"""Read-only database access for the corpus exporter.

Hard rules (mission §0.7 / §0.8):
  * READ ONLY. No INSERT/UPDATE/DELETE anywhere in this package.
  * Never touches publication_task, pipeline_runs state, or anything the
    main pipeline writes.
  * Batched SELECTs with LIMIT/OFFSET on the sessions table; small
    auxiliary tables are fetched whole.
  * utf8mb4, DictCursor, server tz-aware timestamps (no local conversion —
    we emit DB values verbatim; the schema stores local/UTC consistently).
"""

import re
import pymysql
import pymysql.cursors

from . import config as _config


class Database(object):
    def __init__(self, cfg):
        self.cfg = cfg
        self.conn = None

    # ------------------------------------------------------------------
    def connect(self):
        if self.conn is not None:
            return self
        self.conn = pymysql.connect(
            host=self.cfg.db_host,
            port=self.cfg.db_port,
            user=self.cfg.db_user,
            password=self.cfg.db_pass,
            database=self.cfg.db_name,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=15,
            read_timeout=120,
        )
        return self

    def close(self):
        if self.conn is not None:
            try:
                self.conn.close()
            finally:
                self.conn = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------------
    def query(self, sql, args=None):
        """Run a SELECT; return list[dict]. Refuses non-SELECT statements."""
        head = (sql or "").lstrip().split(None, 1)[0].upper() if (sql or "").strip() else ""
        if head not in ("SELECT", "SHOW", "DESCRIBE", "DESC", "WITH"):
            raise RuntimeError("corpus.database: only read statements allowed: %r" % head)
        with self.conn.cursor() as cur:
            cur.execute(sql, args or ())
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def query_one(self, sql, args=None):
        rows = self.query(sql, args)
        return rows[0] if rows else None

    # ------------------------------------------------------------------
    def ping(self):
        """Connectivity + sanity probe (also gives us the live DB version)."""
        row = self.query_one("SELECT VERSION() AS v")
        return row["v"] if row else None

    # ------------------------------------------------------------------
    # Inventory (for the manifest + preflight cross-checks)
    # ------------------------------------------------------------------
    def table_counts(self):
        tables = [
            "radio_programs",
            "radio_program_sessions",
            "llm_output",
            "asr_output",
            "crop_detection",
        ]
        out = {}
        for t in tables:
            row = self.query_one("SELECT COUNT(*) AS n FROM `%s`" % t)
            out[t] = int(row["n"]) if row else None
        return out

    # ------------------------------------------------------------------
    # Bulk fetch — the four content-bearing tables
    # ------------------------------------------------------------------
    PROGRAMS_SQL = (
        "SELECT id, name, url, `time`, time_description, description, "
        "created_at, `start`, radio, radio_id, is_legacy, legacy_expires_at, "
        "crop_offset, crop_enabled, crop_auto "
        "FROM radio_programs ORDER BY id"
    )

    SESSIONS_COLS = (
        "id, program_id, link, created_at, filename, srt_filename, "
        "is_downloaded, status, is_subtitled, attempts, last_error, updated_at"
    )

    def fetch_programs(self):
        return self.query(self.PROGRAMS_SQL)

    def fetch_sessions(self, batch_size=1000, where=None, params=None):
        """Iterate radio_program_sessions in batches (ordered by id).

        where: optional extra WHERE clause (e.g. incremental watermark).
        Yields one row dict at a time; total = (count, generator).
        """
        base_where = "1=1"
        base_params = []
        if where:
            base_where = where
            base_params = list(params or ())
        count_sql = "SELECT COUNT(*) AS n FROM radio_program_sessions WHERE %s" % base_where
        total = int(self.query_one(count_sql, tuple(base_params))["n"])

        def gen():
            offset = 0
            while True:
                sql = (
                    "SELECT %s FROM radio_program_sessions WHERE %s "
                    "ORDER BY id LIMIT %d OFFSET %d"
                    % (self.SESSIONS_COLS, base_where, int(batch_size), int(offset))
                )
                rows = self.query(sql, base_params + [])
                if not rows:
                    break
                for r in rows:
                    yield r
                offset += batch_size
                if offset >= total:
                    break
        return total, gen()

    def fetch_llm_outputs(self, session_ids=None, where=None, params=None):
        """All llm_output rows, batched. session_ids: optional list of ints
        (inlined, never via a subquery — MariaDB 1235 guard)."""
        if session_ids:
            ids = ",".join(str(int(x)) for x in session_ids)
            where = "session_id IN (%s)" % ids
        count_sql = "SELECT COUNT(*) AS n FROM llm_output WHERE %s" % (where or "1=1")
        total = int(self.query_one(count_sql, tuple(params or ()))["n"])

        def gen():
            offset = 0
            while True:
                sql = (
                    "SELECT id, session_id, job_type, model, prompt_id, job_id, "
                    "content, content_en, srt_content, file_relpath, started_at, "
                    "finished_at, status, error, input_tokens, output_tokens "
                    "FROM llm_output WHERE %s ORDER BY id LIMIT 1000 OFFSET %d"
                    % ((where or "1=1"), int(offset))
                )
                rows = self.query(sql, tuple(params or ()))
                if not rows:
                    break
                for r in rows:
                    yield r
                offset += 1000
                if offset >= total:
                    break
        return total, gen()

    def fetch_asr_outputs(self, session_ids=None):
        rows = self.query(
            "SELECT id, session_id, program_id, provider, model_name, "
            "model_version, pipeline_version, audio_sha256, processing_status, "
            "srt_path, fulltext_path, raw_response_path, duration_ms, "
            "segment_count, word_count, latency_ms, rtf, created_at, updated_at, "
            "error_code, error_message FROM asr_output ORDER BY id"
        )
        return rows

    def fetch_crop_detections(self, session_ids=None):
        rows = self.query(
            "SELECT id, session_id, program_id, start_sec, end_sec, confidence, "
            "status, evidence, updated_at FROM crop_detection ORDER BY id"
        )
        return rows

    # ------------------------------------------------------------------
    # Watermark / incremental support (mission §8)
    # ------------------------------------------------------------------
    def high_watermark(self):
        """(max_updated_at, max_session_id) — the incremental cursor.

        Uses sessions.updated_at + id (llm_output has no updated_at, so
        its freshness is tracked via finished_at + id separately).
        """
        row = self.query_one(
            "SELECT MAX(updated_at) AS mu, MAX(id) AS mi FROM radio_program_sessions"
        )
        row2 = self.query_one(
            "SELECT MAX(finished_at) AS mf, MAX(id) AS mi FROM llm_output"
        )
        return {
            "sessions_updated_at": row["mu"].isoformat() if row and row["mu"] else None,
            "sessions_max_id": row["mi"] if row else None,
            "llm_finished_at": row2["mf"].isoformat() if row2 and row2["mf"] else None,
            "llm_max_id": row2["mi"] if row2 else None,
        }

    def watermark_clause(self, wm, overlap_sec):
        """Build the incremental WHERE (mission §8: watermark + overlap).

        Matches a session when:
          * it was updated within [watermark - overlap, +inf], or
          * its id is newer than the watermark max id (inserts), or
          * updated_at is NULL (treat as changed — safer, re-exports are
            idempotent and keyed by record_id).

        Returns (clause, params). The id bound is inlined as an integer
        literal (never a placeholder) per the probe-3 pymysql lessons.
        """
        from datetime import timedelta

        parts = []
        pp = []
        if wm.get("sessions_updated_at"):
            since = _dt_from_iso(wm["sessions_updated_at"][:19])
            if since is not None:
                since = since - timedelta(seconds=int(overlap_sec))
                parts.append("updated_at >= %s")
                pp.append(since)
        if wm.get("sessions_max_id"):
            parts.append("id > %d" % int(wm["sessions_max_id"]))
        if not parts:
            return "1=1", []
        clause = "((updated_at IS NULL) OR " + " OR ".join(parts) + ")"
        return clause, pp

    def changed_session_ids(self, wm, overlap_sec):
        """Strongest available change detection (mission §8 — Stage 4).

        Returns the UNION of session ids that any of these signals say
        have changed since the stored watermark:
          * radio_program_sessions.updated_at >= wm - overlap  (touch)
          * radio_program_sessions.id > wm.max_id              (inserts)
          * llm_output.finished_at >= wm - overlap OR id > wm  (new
            SRT/summary/correction — corrections do NOT bump the
            session's updated_at, so this signal is essential)
          * asr_output.updated_at >= wm - overlap              (ASR)
          * crop_detection.updated_at >= wm - overlap          (crop)
        All id bounds are inlined integer literals (pymysql %d lesson);
        timestamps are bound via %s placeholders. On any single-signal
        query failure the signal is dropped (logged) — the union of the
        remaining signals is still returned (never raises).
        """
        from datetime import timedelta

        signals = {}
        ids = set()

        def since(ts_key):
            ts = wm.get(ts_key)
            if not ts:
                return None
            dt = _dt_from_iso(ts[:19])
            return dt - timedelta(seconds=int(overlap_sec)) if dt else None

        # 1) sessions touch / inserts
        sid = since("sessions_updated_at")
        if sid is not None or wm.get("sessions_max_id") is not None:
            sql = "SELECT DISTINCT id FROM radio_program_sessions WHERE ("
            conds = []
            args = []
            if sid is not None:
                conds.append("updated_at >= %s")
                args.append(sid)
            if wm.get("sessions_max_id") is not None:
                conds.append("id > %d" % int(wm["sessions_max_id"]))
            if conds:
                sql += " OR ".join(conds) + ")"
            try:
                for r in self.query(sql, tuple(args)):
                    ids.add(int(r["id"]))
            except Exception as e:  # noqa: BLE001
                signals["sessions"] = "error: %s" % e
        signals.setdefault("sessions", "ok")

        # 2) llm_output freshness (new/corrected SRTs, summaries, ...)
        lid = wm.get("llm_max_id")
        lsince = since("llm_finished_at")
        if lid is not None or lsince is not None:
            sql = "SELECT DISTINCT session_id FROM llm_output WHERE ("
            conds = []
            args = []
            if lsince is not None:
                conds.append("finished_at >= %s")
                args.append(lsince)
            if lid is not None:
                conds.append("id > %d" % int(lid))
            if conds:
                sql += " OR ".join(conds) + ")"
            try:
                for r in self.query(sql, tuple(args)):
                    if r.get("session_id") is not None:
                        ids.add(int(r["session_id"]))
            except Exception as e:  # noqa: BLE001
                signals["llm"] = "error: %s" % e
        signals.setdefault("llm", "ok")

        # 3) asr_output freshness (updated_at only — no id watermark
        #    tracked for asr; overlap window covers the gap)
        asince = since("sessions_updated_at")
        if asince is not None:
            try:
                for r in self.query(
                        "SELECT DISTINCT session_id FROM asr_output "
                        "WHERE updated_at >= %s", (asince,)):
                    if r.get("session_id") is not None:
                        ids.add(int(r["session_id"]))
            except Exception as e:  # noqa: BLE001
                signals["asr"] = "error: %s" % e
        signals.setdefault("asr", "ok")

        # 4) crop_detection freshness (same approach as asr)
        csince = since("sessions_updated_at")
        if csince is not None:
            try:
                for r in self.query(
                        "SELECT DISTINCT session_id FROM crop_detection "
                        "WHERE updated_at >= %s", (csince,)):
                    if r.get("session_id") is not None:
                        ids.add(int(r["session_id"]))
            except Exception as e:  # noqa: BLE001
                signals["crop"] = "error: %s" % e
        signals.setdefault("crop", "ok")

        return sorted(ids), signals

    # ------------------------------------------------------------------
    # URL / identity regex helpers (single home for the patterns)
    # ------------------------------------------------------------------
    RE_CH = re.compile(r"[?&]ch=(\d+)")
    RE_E = re.compile(r"[?&]e=(\d+)")
    RE_M = re.compile(r"[?&]m=(\d+)")

    @classmethod
    def parse_ch(cls, url):
        m = cls.RE_CH.search(url or "")
        return int(m.group(1)) if m else None

    @classmethod
    def parse_e(cls, url):
        m = cls.RE_E.search(url or "")
        return m.group(1) if m else None

    @classmethod
    def parse_m(cls, url):
        m = cls.RE_M.search(url or "")
        return m.group(1) if m else None

    @classmethod
    def record_id_for(cls, session):
        """Stable identity (data model §2)."""
        e = cls.parse_e(session.get("link"))
        ch = cls.parse_ch(session.get("link"))
        if ch is not None and e is not None:
            return "iranseda:ch%d:e%s" % (ch, e)
        return "iranseda:db%s:s%d" % (
            session.get("program_id") if session.get("program_id") is not None else "x",
            int(session.get("id") or 0),
        )


def _dt_from_iso(s):
    from datetime import datetime
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    return None
