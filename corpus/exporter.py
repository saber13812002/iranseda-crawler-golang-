"""Exporter: orchestrates DB + disk -> corpus.jsonl + manifest + stats.

Writes (all under cfg.out_dir):
  corpus.jsonl            (or corpus-0001.jsonl... when sharded)
  quarantine.jsonl        Class B identity-collision records, preserved
                          permanently with the quarantine policy (mission:
                          PERMANENT QUARANTINE UNTIL IDENTITY IS PROVEN)
  invalid.jsonl           records with STRUCTURAL validation problems —
                          never dropped silently; kept for repair
  manifest.json           (counts, watermark, config, fingerprints)
  stats.json              (per-status / per-job-type / disk-join stats)
  checksums.sha256        sha256sum-format hashes of the data files

Atomicity (mission §5): a run builds ALL of its outputs in a staging
directory (cfg.out_dir/.staging.<run_id>), validates the staged corpus,
archives the currently-live export files into a retention slot
(cfg.out_dir/previous/<run_id>/), and only then promotes the staged files
into place. A failed run never touches the live outputs. The previous
export is never deleted — the last PREVIOUS_RETENTION slots are kept.

Determinism: pass run_id + exported_at (e.g. pinned to the DB high
watermark via --deterministic) and two runs over unchanged data produce
byte-identical data files (corpus/quarantine/invalid/stats) and identical
checksums.sha256. manifest.json is a run record and differs only in
duration_sec (wall clock).
"""

import os
import re
import json
import time
import hashlib
import shutil
import datetime

from . import database as _db
from . import extractor as _extractor
from . import mapper as _mapper
from . import validator as _validator


# Class B quarantine (Stage 1 policy — never delete/merge/reclassify).
QUARANTINE_POLICY = "PERMANENT_UNTIL_IDENTITY_PROVEN"
QUARANTINE_REF = "reports/corpus/STAGE_1_CLASS_B_IDENTITY_REPORT.md"

# Live export files that get archived into previous/ + promoted.
_LIVE_RE = re.compile(r"^(corpus\.jsonl|corpus-\d{4}\.jsonl|invalid\.jsonl"
                      r"|quarantine\.jsonl|manifest\.json|stats\.json)$")

# Data files covered by checksums.sha256. manifest.json is a run record
# (wall-clock duration_sec / scanned_at) and is excluded on purpose.
_CHECKSUM_NAMES = ("corpus.jsonl", "invalid.jsonl", "quarantine.jsonl",
                   "stats.json")


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _atomic_write(path, data):
    tmp = path + ".tmp"
    if isinstance(data, str):
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(data)
    else:
        with open(tmp, "wb") as f:
            f.write(data)
    os.replace(tmp, path)


def _sha256_of_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_duplicate_record_id(problems):
    return any("duplicate record_id" in p for p in problems)


# ----------------------------------------------------------------------
# Exclusive job lock (mission §8 — Stage 4: exactly ONE corpus export at
# a time, across `export`, `incremental`, `reconcile` and the scheduler).
# Pidfile with stale detection: signal 0 is a pure existence check
# (no signal is delivered), so a dead holder's lock is taken over.
# ----------------------------------------------------------------------
LOCK_FILE = "export.lock"


class NoLiveCorpusError(RuntimeError):
    """Incremental merge was requested but there is no live corpus to
    merge into — the caller must fall back to a full export."""


def _pid_alive(pid):
    """Best-effort liveness check for the lock holder pid.

    NOTE: os.kill(pid, 0) is NOT a pure existence check on Windows —
    signal 0 == CTRL_C_EVENT, which would deliver a Ctrl+C to the
    console group. On Windows use OpenProcess instead: a handle is
    returned iff the process exists (access-denied still means the
    process exists but is invisible -> treat as alive, safe side).
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        PROCESS_QUERY_INFORMATION = 0x0400
        h = k32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
        if h:
            k32.CloseHandle(h)
            return True
        if k32.GetLastError() == 5:  # ERROR_ACCESS_DENIED -> exists
            return True
        return False
    try:
        os.kill(pid, 0)  # unix: signal 0 is a pure existence check
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by another uid
    except OSError:
        return False


def _acquire_export_lock(cfg, log=None):
    """Acquire <out_dir>/export.lock. Returns True when this process now
    holds it. A lock whose pid is dead (or unreadable) is stale and is
    taken over; a lock held by a live foreign pid refuses the export."""
    log = log or (lambda m: None)
    path = os.path.join(cfg.out_dir, LOCK_FILE)
    os.makedirs(cfg.out_dir, exist_ok=True)
    if os.path.exists(path):
        old = None
        try:
            with open(path, encoding="utf-8") as f:
                old = int((f.read().strip() or "0").split()[0])
        except (ValueError, OSError, IndexError):
            old = None
        if old is not None and old != os.getpid() and _pid_alive(old):
            log("exporter: %s held by pid %d — another export in progress; "
                "aborting" % (LOCK_FILE, old))
            return False
        log("exporter: taking over stale %s (old pid %s)" % (LOCK_FILE, old))
    with open(path, "w", encoding="utf-8") as f:
        f.write("%d %s" % (os.getpid(), _now_iso()))
    return True


def _release_export_lock(cfg):
    path = os.path.join(cfg.out_dir, LOCK_FILE)
    # NOTE: read the holder BEFORE removing — on Windows os.remove fails
    # (WinError 32) while the file still has an open handle.
    holder = None
    try:
        with open(path, encoding="utf-8") as f:
            holder = f.read().strip().split()[0]
    except (OSError, IndexError, ValueError):
        return
    if holder == str(os.getpid()):
        try:
            os.remove(path)
        except OSError:
            pass


class Exporter(object):
    # how many previous/<run_id> slots to keep after each successful run
    PREVIOUS_RETENTION = 3

    def __init__(self, db, cfg, disk=None, log=print):
        self.db = db
        self.cfg = cfg
        self.log = log
        self.ex = _extractor.Extractor(db, cfg, disk=disk)

    # ------------------------------------------------------------------
    # path helpers
    # ------------------------------------------------------------------
    def previous_dir(self):
        return os.path.join(self.cfg.out_dir, "previous")

    def live_output_files(self):
        """Names of the live export files currently in cfg.out_dir."""
        if not os.path.isdir(self.cfg.out_dir):
            return []
        return sorted(n for n in os.listdir(self.cfg.out_dir)
                      if _LIVE_RE.match(n))

    def read_checksums(self):
        """Parse checksums.sha256 -> {filename: hex digest}."""
        p = os.path.join(self.cfg.out_dir, "checksums.sha256")
        out = {}
        if not os.path.exists(p):
            return out
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                digest, name = line.split(None, 1)
                out[name.lstrip("*")] = digest
        return out

    # ------------------------------------------------------------------
    # staging / retention / promotion
    # ------------------------------------------------------------------
    def _clean_staging(self, staging):
        if os.path.isdir(staging):
            shutil.rmtree(staging, ignore_errors=True)
        os.makedirs(staging)

    def _validate_staged(self, stage_files, n_ok, n_invalid, n_quarantine):
        """Re-read the staged output and validate it before promotion.

        corpus lines are re-validated with a FRESH seen set (the duplicate
        check already happened during the build); quarantine lines are
        checked one-by-one so the colliding record_ids do not trip the
        duplicate rule here.
        """
        def check(path, label, shared):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    probs = _validator.validate_record(obj, seen_ids=shared)
                    if probs:
                        raise RuntimeError("staged %s validation failed: %s"
                                           % (label, probs))

        def line_count(path):
            with open(path, encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())

        shared = set()
        corpus_paths = stage_files["corpus"]
        if isinstance(corpus_paths, str):
            corpus_paths = [corpus_paths]
        for p in corpus_paths:
            check(p, "corpus", shared)
        total = sum(line_count(p) for p in corpus_paths)
        if total != n_ok:
            raise RuntimeError("staged corpus line count %d != expected %d"
                               % (total, n_ok))
        if stage_files.get("invalid"):
            def check_invalid(path, label, shared):
                with open(path, encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        wrapper = json.loads(line)
                        rec = wrapper.get("record")
                        if not isinstance(rec, dict):
                            raise RuntimeError(
                                "staged invalid line has no 'record': %r"
                                % line[:120])
                        probs = _validator.validate_record(rec)
                        # problems ARE expected here — that is why the
                        # record is invalid; re-validation must at least be
                        # structurally consistent (no NEW required-key
                        # failures beyond the recorded problems).
                        structural = [
                            p for p in probs
                            if "missing required key" in p
                            and p not in wrapper.get("problems", [])]
                        if structural:
                            raise RuntimeError(
                                "staged invalid record structurally broken: %s"
                                % structural)

            check_invalid(stage_files["invalid"], "invalid", set())
            inv_count = line_count(stage_files["invalid"])
            if inv_count != n_invalid:
                raise RuntimeError("staged invalid line count %d != expected %d"
                                   % (inv_count, n_invalid))
        if stage_files.get("quarantine"):
            with open(stage_files["quarantine"], encoding="utf-8") as f:
                qcount = 0
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    qcount += 1
                    obj = json.loads(line)
                    probs = _validator.validate_record(obj["record"])
                    # the duplicate-record_id problem is EXPECTED here — it
                    # is exactly what quarantined the record; anything else
                    # is a real structural failure.
                    unexpected = [p for p in probs
                                  if "duplicate record_id" not in p]
                    if unexpected:
                        raise RuntimeError(
                            "staged quarantine record structurally invalid: %s"
                            % unexpected)
            if qcount != n_quarantine:
                raise RuntimeError(
                    "staged quarantine line count %d != expected %d"
                    % (qcount, n_quarantine))

    def _archive_live(self):
        """Move the currently-live export files into previous/<old-run>/.

        The slot is named after the OLD run (from the live manifest.json)
        so each slot self-identifies what it contains. Returns the slot
        name, or None if there is no previous live export.
        """
        names = self.live_output_files()
        if not names:
            return None
        old_run = None
        live_manifest = os.path.join(self.cfg.out_dir, "manifest.json")
        if os.path.exists(live_manifest):
            try:
                with open(live_manifest, encoding="utf-8") as f:
                    old_run = json.load(f).get("run_id")
            except (ValueError, OSError):
                old_run = None
        if not old_run:
            old_run = "orphan-%s" % datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        slot = old_run
        if os.path.isdir(os.path.join(self.previous_dir(), slot)):
            # never clobber an existing slot: suffix a counter
            i = 2
            while os.path.isdir(os.path.join(self.previous_dir(),
                                             "%s-%d" % (slot, i))):
                i += 1
            slot = "%s-%d" % (slot, i)
        dest = os.path.join(self.previous_dir(), slot)
        os.makedirs(dest, exist_ok=True)
        for name in names:
            shutil.move(os.path.join(self.cfg.out_dir, name),
                        os.path.join(dest, name))
        return slot

    def _promote(self, staging):
        for name in sorted(os.listdir(staging)):
            os.replace(os.path.join(staging, name),
                       os.path.join(self.cfg.out_dir, name))
        shutil.rmtree(staging, ignore_errors=True)

    def _write_checksums(self):
        """Write checksums.sha256 (sha256sum format) for the data files."""
        lines = []
        for name in self.live_output_files():
            if name == "corpus.jsonl" or (name.startswith("corpus-")
                                          and name.endswith(".jsonl")) \
               or name in _CHECKSUM_NAMES:
                lines.append("%s  %s" % (_sha256_of_file(
                    os.path.join(self.cfg.out_dir, name)), name))
        path = os.path.join(self.cfg.out_dir, "checksums.sha256")
        _atomic_write(path, "\n".join(lines) + "\n")
        return [ln.split(None, 1)[1] for ln in lines]

    def _prune_previous(self):
        prev = self.previous_dir()
        if not os.path.isdir(prev):
            return
        slots = sorted(n for n in os.listdir(prev)
                       if os.path.isdir(os.path.join(prev, n)))
        for slot in slots[:-self.PREVIOUS_RETENTION]:
            shutil.rmtree(os.path.join(prev, slot), ignore_errors=True)

    # ------------------------------------------------------------------
    def run(self, where=None, params=None, limit=None, run_id=None,
            exported_at=None):
        """Full (or filtered) export. Returns the manifest dict.

        exported_at: fixed timestamp for deterministic builds; when given,
        the manifest's exported_at and every record's provenance.exported_at
        use this value (pin it to the DB watermark for reproducible builds).
        """
        t0 = time.time()
        deterministic = exported_at is not None
        if exported_at is None:
            exported_at = _now_iso()
        if run_id is None:
            if deterministic:
                # run_id derives from the pinned timestamp: unchanged data
                # (same DB watermark anchor) -> same run_id -> byte-identical.
                # ':' replaced so the run_id is filesystem-safe everywhere.
                run_id = "corpus-det-%s" % (exported_at
                                             .replace(" ", "T")
                                             .replace(":", "-"))
            else:
                run_id = ("corpus-%s"
                          % datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))

        os.makedirs(self.cfg.out_dir, exist_ok=True)
        if not _acquire_export_lock(self.cfg, self.log):
            raise RuntimeError(
                "export.lock held by another live process — "
                "refusing to run a concurrent export")
        try:
            self._run_slot = run_id
            staging = os.path.join(self.cfg.out_dir, ".staging.%s" % run_id)
            self._clean_staging(staging)
            try:
                return self._run_inner(staging, where=where, params=params,
                                        limit=limit, run_id=run_id,
                                        exported_at=exported_at,
                                        deterministic=deterministic, t0=t0)
            except Exception:
                # a failed run must never leave staging debris behind and,
                # crucially, never touched the live outputs
                shutil.rmtree(staging, ignore_errors=True)
                raise
        finally:
            _release_export_lock(self.cfg)

    # ------------------------------------------------------------------
    def _commit(self, staging, stage_files, n_ok, n_invalid, n_quarantine,
                manifest, t0):
        """Shared atomic tail of every export path (full, incremental
        merge): validate staged output -> archive live into previous/ ->
        rewrite manifest (previous_export + duration) -> promote ->
        checksums -> retention pruning. Returns the manifest."""
        self._validate_staged(stage_files, n_ok, n_invalid, n_quarantine)
        prev_slot = self._archive_live()
        manifest["previous_export"] = (
            None if prev_slot is None else "previous/" + prev_slot)
        manifest["duration_sec"] = round(time.time() - t0, 1)
        _atomic_write(os.path.join(staging, "manifest.json"),
                      json.dumps(manifest, indent=2, ensure_ascii=False))
        self._promote(staging)
        manifest["checksums_files"] = self._write_checksums()
        self._prune_previous()
        return manifest

    def _load_lookup_tables(self):
        """(prog_by_id, prog_by_chm, llm_by_session, asr_by_session,
        crop_by_session) — dimension tables, loaded once per build."""
        prog_by_id, prog_by_chm = self.ex.load_programs()
        llm_by_session, _llm_total = self.ex.load_llm_outputs()
        asr_by_session = self.ex.load_asr_outputs()
        crop_by_session = self.ex.load_crop_detections()
        return (prog_by_id, prog_by_chm, llm_by_session, asr_by_session,
                crop_by_session)

    # ------------------------------------------------------------------
    def _build_session_slice(self, gen, total_sessions, staging, run_id,
                             exported_at):
        """Map the given session iterator to records and write them to the
        staging corpus file (single or sharded). Validation runs with a
        FRESH seen set: duplicates inside the slice -> quarantine (Stage 3
        contract). Returns {n, n_ok, n_invalid, n_quarantine, out_path,
        shard_paths, stats}."""
        (prog_by_id, prog_by_chm, llm_by_session,
         asr_by_session, crop_by_session) = self._load_lookup_tables()
        out_path = None
        shard_paths = []
        f = None
        n = 0
        n_ok = 0
        n_invalid = 0
        n_quarantine = 0
        quarantine_path = os.path.join(staging, "quarantine.jsonl")
        invalid_path = os.path.join(staging, "invalid.jsonl")
        inv = None
        qar = None
        seen_ids = set()
        stats = self._init_stats()

        shard_size = self.cfg.shard_lines
        if shard_size > 0:
            def new_shard():
                global_idx = len(shard_paths)
                p = os.path.join(staging, "corpus-%04d.jsonl" % (global_idx + 1))
                shard_paths.append(p)
                return open(p, "w", encoding="utf-8", newline="\n")
            f = new_shard()
            shard_count_in_file = 0
        else:
            out_path = os.path.join(staging, "corpus.jsonl")
            f = open(out_path, "w", encoding="utf-8", newline="\n")
            shard_count_in_file = 0

        try:
            for session in gen:
                rec = _mapper.build_record(
                    session, prog_by_id, prog_by_chm,
                    llm_by_session.get(session["id"], []),
                    asr_by_session.get(session["id"], []),
                    crop_by_session.get(session["id"]),
                    self.ex.disk, self.cfg, run_id, exported_at,
                )
                n += 1
                probs = _validator.validate_record(rec, seen_ids=seen_ids)
                if probs:
                    if _is_duplicate_record_id(probs):
                        # Class B: identity collision — permanent
                        # quarantine, preserved with the full record.
                        n_quarantine += 1
                        if qar is None:
                            qar = open(quarantine_path, "w",
                                       encoding="utf-8", newline="\n")
                        qar.write(json.dumps({
                            "record": rec,
                            "problems": probs,
                            "quarantine": {
                                "policy": QUARANTINE_POLICY,
                                "class": "B",
                                "reason": "identity collision (duplicate record_id)",
                                "session_id": rec.get("database_refs", {}).get("session_id"),
                                "record_id": rec.get("record_id"),
                                "investigation_ref": QUARANTINE_REF,
                                "quarantined_at": exported_at,
                            },
                        }, ensure_ascii=False) + "\n")
                    else:
                        n_invalid += 1
                        if inv is None:
                            inv = open(invalid_path, "w",
                                       encoding="utf-8", newline="\n")
                        inv.write(json.dumps({"record": rec, "problems": probs},
                                             ensure_ascii=False) + "\n")
                    continue
                n_ok += 1
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                if shard_size > 0:
                    shard_count_in_file += 1
                    if shard_count_in_file >= shard_size:
                        f.close()
                        f = new_shard()
                        shard_count_in_file = 0
                stats = self._bump_stats(stats, rec)
                if n % 500 == 0:
                    self.log("exporter: %d/%d sessions..." % (n, total_sessions))
        finally:
            f.close()
            if inv is not None:
                inv.close()
            if qar is not None:
                qar.close()

        return {
            "n": n,
            "n_ok": n_ok,
            "n_invalid": n_invalid,
            "n_quarantine": n_quarantine,
            "out_path": out_path,
            "shard_paths": shard_paths,
            "invalid_path": invalid_path if os.path.exists(invalid_path) else None,
            "quarantine_path": (quarantine_path
                                if os.path.exists(quarantine_path) else None),
            "stats": stats,
        }

    # ------------------------------------------------------------------
    def _build_manifest(self, staging, ns, total_sessions, wm, counts,
                        run_id, exported_at, mode, deterministic, extra=None):
        """Staged manifest.json + stats.json, shared by the full and the
        incremental-merge paths. ns = the build namespace dict (see
        _build_session_slice / _run_incremental_inner)."""
        scanned_at = self.ex.disk.scanned_at
        if deterministic:
            # wall-clock epoch float -> keep data fields reproducible
            scanned_at = "frozen: pinned to run's disk scan (deterministic)"
        manifest = {
            "schema_version": "1.0",
            "run_id": run_id,
            "exported_at": exported_at,
            "mode": mode,
            "deterministic": deterministic,
            "records_written": ns["n_ok"],
            "records_invalid": ns["n_invalid"],
            "records_quarantined": ns["n_quarantine"],
            "sessions_seen": ns["n"],
            "sessions_total_in_db": total_sessions,
            "output_files": ([os.path.join(self.cfg.out_dir, "corpus.jsonl")]
                             if ns["out_path"]
                             else [os.path.join(self.cfg.out_dir,
                                                 "corpus-%04d.jsonl" % (i + 1))
                                   for i in range(len(ns["shard_paths"]))]),
            "shard_lines": self.cfg.shard_lines,
            "quarantine_file": "quarantine.jsonl" if ns["quarantine_path"] else None,
            "invalid_file": "invalid.jsonl" if ns["invalid_path"] else None,
            "quarantine_policy": QUARANTINE_POLICY,
            "quarantine_ref": QUARANTINE_REF,
            "checksums_file": "checksums.sha256",
            "previous_export": None,  # filled after archiving
            "db_counts_at_run": counts,
            "watermark": wm,
            "disk": {
                "scanned_at": scanned_at,
                "files_indexed": self.ex.disk.counts["files"],
                "stems_indexed": self.ex.disk.counts["stems"],
                "scan_errors": self.ex.disk.counts["errors"],
            },
            "config": self.cfg.to_dict(),
            "fingerprint_note": "per-record fingerprints in stats.fingerprints_sample",
        }
        if extra:
            manifest.update(extra)
        _atomic_write(os.path.join(staging, "manifest.json"),
                      json.dumps(manifest, indent=2, ensure_ascii=False))
        _atomic_write(os.path.join(staging, "stats.json"),
                      json.dumps(ns["stats"], indent=2, ensure_ascii=False))
        return manifest

    # ------------------------------------------------------------------
    def _run_inner(self, staging, where, params, limit, run_id, exported_at,
                   deterministic, t0):
        counts = self.db.table_counts()
        wm = self.db.high_watermark()
        if deterministic:
            # keep data fields reproducible; the DB watermark is the anchor
            wm = dict(wm)
            wm["note"] = ("frozen: deterministic build pinned to DB "
                          "high watermark")

        total_sessions, gen = self.db.fetch_sessions(where=where, params=params)
        if limit is not None:
            # bounded iteration for pilots (wrap the already-open iterator)
            _unbounded = gen

            def _limited():
                for _i, r in enumerate(_unbounded):
                    if _i >= limit:
                        break
                    yield r

            gen = _limited()

        ns = self._build_session_slice(gen, total_sessions, staging,
                                       run_id, exported_at)
        manifest = self._build_manifest(
            staging, ns, total_sessions, wm, counts, run_id, exported_at,
            mode="incremental" if where else "full",
            deterministic=deterministic)
        stage_files = {
            "corpus": ns["out_path"] if ns["out_path"] else ns["shard_paths"],
            "invalid": ns["invalid_path"],
            "quarantine": ns["quarantine_path"],
        }
        manifest = self._commit(staging, stage_files, ns["n_ok"],
                                 ns["n_invalid"], ns["n_quarantine"],
                                 manifest, t0)
        self.log("exporter: done in %ss — %d ok, %d invalid, %d quarantined, "
                 "%d seen (total %d)"
                 % (manifest["duration_sec"], ns["n_ok"], ns["n_invalid"],
                    ns["n_quarantine"], ns["n"], total_sessions))
        return manifest

    # ------------------------------------------------------------------
    # Incremental MERGE path (mission §8 — Stage 4)
    # ------------------------------------------------------------------
    def run_incremental(self, where, params=None, run_id=None,
                        exported_at=None, extra=None):
        """Merge-based incremental export (Stage 4).

        Exports ONLY the changed-session slice (caller supplies WHERE)
        and merges it INTO the currently-live corpus by record_id — the
        live corpus is never replaced by the slice:

          * slice records replace/insert into the live corpus by
            record_id (a correction updates the SAME record)
          * a slice record whose record_id already exists in the live
            corpus under a DIFFERENT session goes to quarantine (a
            cross-run collision; first-seen wins; never merged or
            reclassified — Class B policy)
          * quarantine/invalid entries merge keyed by
            (record_id, session_id); the slice wins per key, untouched
            live entries are preserved (permanent quarantine)
          * NOTHING is ever physically deleted — a session that
            disappears from the DB stays in the corpus until a
            reconcile records its removal

        The merged output goes through the same atomic commit pipeline
        as a full export (validate staged -> archive live -> promote).
        Raises NoLiveCorpusError when there is no live corpus to merge
        into (the caller falls back to a full export). `extra` is an
        optional dict merged into the manifest (e.g. the change-detection
        signals).
        """
        t0 = time.time()
        deterministic = exported_at is not None
        if exported_at is None:
            exported_at = _now_iso()
        if run_id is None:
            run_id = ("corpus-inc-%s"
                      % datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
        os.makedirs(self.cfg.out_dir, exist_ok=True)
        if not _acquire_export_lock(self.cfg, self.log):
            raise RuntimeError(
                "export.lock held by another live process — "
                "refusing to run a concurrent export")
        try:
            return self._run_incremental_inner(
                where=where, params=params, run_id=run_id,
                exported_at=exported_at, deterministic=deterministic,
                extra=extra, t0=t0)
        finally:
            _release_export_lock(self.cfg)

    def _run_incremental_inner(self, where, params, run_id, exported_at,
                               deterministic, extra, t0):
        # --- 1) live corpus to merge into (guard: must exist) ----------
        live_records = self.read_output()
        if not live_records:
            raise NoLiveCorpusError(
                "no live corpus.jsonl to merge into — run a full export "
                "first")
        live_by_id = {r["record_id"]: r for r in live_records}
        live_q = self._read_live_side_file("quarantine.jsonl")
        live_i = self._read_live_side_file("invalid.jsonl")

        # --- 2) export the changed slice into staging ------------------
        staging = os.path.join(self.cfg.out_dir, ".staging.%s" % run_id)
        self._clean_staging(staging)
        try:
            total_sessions, gen = self.db.fetch_sessions(
                where=where, params=params)
            ns = self._build_session_slice(gen, total_sessions, staging,
                                           run_id, exported_at)

            # --- 3) merge slice into live corpus by record_id ----------
            merged = {}
            for rid, rec in live_by_id.items():
                sid = (rec.get("database_refs") or {}).get("session_id")
                merged[(sid, rid)] = rec
            merged_q = dict(live_q)
            merged_i = dict(live_i)

            # the slice's own quarantine/invalid entries replace the
            # live entry with the same key
            merged_q.update(self._read_side_lines(ns["quarantine_path"]))
            merged_i.update(self._read_side_lines(ns["invalid_path"]))

            n_cross_collision = 0
            for rid, line in self._read_corpus_lines(
                    ns["out_path"], ns["shard_paths"]).items():
                rec = json.loads(line)
                sid = (rec.get("database_refs") or {}).get("session_id")
                if rid in live_by_id:
                    live_sid = ((live_by_id[rid].get("database_refs")
                                 or {}).get("session_id"))
                    if live_sid != sid:
                        # cross-run collision: the LIVE record stays
                        # (first-seen wins); this record is preserved in
                        # quarantine.jsonl permanently — never merged or
                        # reclassified.
                        n_cross_collision += 1
                        merged_q[(rid, sid)] = json.dumps({
                            "record": rec,
                            "problems": [
                                "duplicate record_id across export runs: %s"
                                % rid],
                            "quarantine": {
                                "policy": QUARANTINE_POLICY,
                                "class": "B",
                                "reason": ("identity collision across "
                                           "export runs (duplicate "
                                           "record_id)"),
                                "session_id": sid,
                                "record_id": rid,
                                "investigation_ref": QUARANTINE_REF,
                                "quarantined_at": exported_at,
                            },
                        }, ensure_ascii=False)
                        continue
                merged[(sid, rid)] = rec
                live_by_id[rid] = rec

            # --- 4) write the merged staged output ----------------------
            merged_items = sorted(
                merged.items(),
                key=lambda kv: (kv[0][0] is None, kv[0][0] or 0,
                                 kv[0][1] or ""))
            m_out, m_shards = self._write_merged_corpus(
                staging, [rec for _k, rec in merged_items])
            m_qar = os.path.join(staging, "quarantine.jsonl")
            m_inv = os.path.join(staging, "invalid.jsonl")
            self._write_side_file(m_qar, merged_q)
            self._write_side_file(m_inv, merged_i)

            # stats recomputed from the MERGED corpus
            stats = self._init_stats()
            for _k, rec in merged_items:
                stats = self._bump_stats(stats, rec)

            m_ns = {
                "n": ns["n"],
                "n_ok": len(merged_items),
                "n_invalid": len(merged_i),
                "n_quarantine": len(merged_q),
                "out_path": m_out,
                "shard_paths": m_shards,
                "invalid_path": m_inv if os.path.exists(m_inv) else None,
                "quarantine_path": (m_qar if os.path.exists(m_qar) else None),
                "stats": stats,
            }

            wm = self.db.high_watermark()
            counts = self.db.table_counts()
            extra2 = dict(extra or {})
            extra2["incremental"] = {
                "changed_sessions_seen": ns["n"],
                "records_before": len(live_records),
                "records_after": len(merged_items),
                "quarantined_before": len(live_q),
                "quarantined_after": len(merged_q),
                "invalid_before": len(live_i),
                "invalid_after": len(merged_i),
                "cross_run_collisions": n_cross_collision,
            }
            manifest = self._build_manifest(
                staging, m_ns, total_sessions, wm, counts, run_id,
                exported_at, mode="incremental",
                deterministic=deterministic, extra=extra2)
            stage_files = {
                "corpus": m_out if m_out else m_shards,
                "invalid": m_ns["invalid_path"],
                "quarantine": m_ns["quarantine_path"],
            }
            manifest = self._commit(staging, stage_files, m_ns["n_ok"],
                                     m_ns["n_invalid"], m_ns["n_quarantine"],
                                     manifest, t0)
            self.log("exporter: incremental merge done in %ss — %d -> %d "
                     "records (%d changed sessions, %d cross-run "
                     "collisions quarantined)"
                     % (manifest["duration_sec"], len(live_records),
                        len(merged_items), ns["n"], n_cross_collision))
            return manifest
        finally:
            # a failed merge never touches live outputs (as in the full
            # path): staging is cleaned, live files stay intact
            if os.path.isdir(staging):
                shutil.rmtree(staging, ignore_errors=True)

    # ------------------------------------------------------------------
    # side-file / corpus-line readers for the merge path
    # ------------------------------------------------------------------
    @staticmethod
    def _side_key(wrapper):
        rec = wrapper.get("record") or {}
        return (rec.get("record_id"),
                (rec.get("database_refs") or {}).get("session_id"))

    def _read_live_side_file(self, name):
        """Live quarantine.jsonl / invalid.jsonl as {(rid, sid): line}."""
        out = {}
        p = os.path.join(self.cfg.out_dir, name)
        if not os.path.exists(p):
            return out
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    w = json.loads(line)
                except ValueError:
                    continue
                out[self._side_key(w)] = line
        return out

    @staticmethod
    def _read_side_lines(path):
        if not path or not os.path.exists(path):
            return {}
        out = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    w = json.loads(line)
                except ValueError:
                    continue
                out[Exporter._side_key(w)] = line
        return out

    @staticmethod
    def _read_corpus_lines(out_path, shard_paths):
        paths = [out_path] if out_path else list(shard_paths or [])
        out = {}
        for p in paths:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    out[json.loads(line)["record_id"]] = line
        return out

    def _write_merged_corpus(self, staging, records):
        """Write the merged corpus into staging (replacing the slice
        corpus files). Returns (out_path, shard_paths)."""
        for name in os.listdir(staging):
            if name == "corpus.jsonl" or (name.startswith("corpus-")
                                          and name.endswith(".jsonl")):
                os.remove(os.path.join(staging, name))
        lines = [json.dumps(rec, ensure_ascii=False) for rec in records]
        shard_size = self.cfg.shard_lines
        if shard_size > 0:
            shard_paths = []
            for i in range(0, max(1, len(lines)), shard_size):
                p = os.path.join(staging,
                                 "corpus-%04d.jsonl" % (len(shard_paths) + 1))
                with open(p, "w", encoding="utf-8", newline="\n") as f:
                    for ln in lines[i:i + shard_size]:
                        f.write(ln + "\n")
                shard_paths.append(p)
            return None, shard_paths
        out_path = os.path.join(staging, "corpus.jsonl")
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            for ln in lines:
                f.write(ln + "\n")
        return out_path, []

    @staticmethod
    def _write_side_file(path, entries):
        """Write {(key): line} in key order; remove the file if empty."""
        if not entries:
            if os.path.exists(path):
                os.remove(path)
            return
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for key in sorted(entries, key=lambda k: (k[0] or "", k[1] or 0)):
                f.write(entries[key] + "\n")

    # ------------------------------------------------------------------
    @staticmethod
    def _init_stats():
        return {
            "by_status": {},
            "by_job_type": {},
            "by_model": {},
            "records_with_broadcast": 0,
            "records_without_broadcast": 0,
            "records_with_original_srt": 0,
            "records_with_original_txt": 0,
            "records_with_corrected_srt": 0,
            "records_with_corrected_txt": 0,
            "records_with_summary": 0,
            "records_with_full_text": 0,
            "records_with_qa": 0,
            "records_complete": 0,
            "records_with_warnings": 0,
            "warning_kinds": {},
            "missing_kinds": {},
            "audio_local_exists": 0,
            "episode_key_link": 0,
            "episode_key_fallback": 0,
            "program_missing": 0,
            "fingerprints_sample": {},
        }

    @staticmethod
    def _bump_stats(s, rec):
        st = rec["pipeline_state"].get("status") or "null"
        s["by_status"][st] = s["by_status"].get(st, 0) + 1
        s["records_with_broadcast" if rec["broadcast"] else "records_without_broadcast"] += 1
        if rec["transcripts"]["originals"]["srt"]["exists"]:
            s["records_with_original_srt"] += 1
        if rec["transcripts"]["originals"]["txt"]["exists"]:
            s["records_with_original_txt"] += 1
        jts = set()
        for lo in rec["transcripts"]["llm_outputs"]:
            jt = lo["job_type"]
            jts.add(jt)
            s["by_job_type"][jt] = s["by_job_type"].get(jt, 0) + 1
            model = lo.get("model") or "null"
            s["by_model"][model] = s["by_model"].get(model, 0) + 1
        if "correct_subtitles" in jts:
            s["records_with_corrected_srt"] += 1
        if "correct_text" in jts:
            s["records_with_corrected_txt"] += 1
        if "summary" in jts:
            s["records_with_summary"] += 1
        if "full_text" in jts:
            s["records_with_full_text"] += 1
        if "qa" in jts:
            s["records_with_qa"] += 1
        if rec["audio"].get("local_exists"):
            s["audio_local_exists"] += 1
        if rec["episode_key"]["source"] == "link":
            s["episode_key_link"] += 1
        else:
            s["episode_key_fallback"] += 1
        if "program" in rec["quality"]["missing"]:
            s["program_missing"] += 1
        for w in rec["quality"]["warnings"]:
            key = w.split(":", 1)[0]
            s["warning_kinds"][key] = s["warning_kinds"].get(key, 0) + 1
        for m in rec["quality"]["missing"]:
            key = m.split(":", 1)[0]
            s["missing_kinds"][key] = s["missing_kinds"].get(key, 0) + 1
        if rec["quality"]["warnings"]:
            s["records_with_warnings"] += 1
        if not rec["quality"]["missing"]:
            s["records_complete"] += 1
        if len(s["fingerprints_sample"]) < 200:
            s["fingerprints_sample"][rec["record_id"]] = _mapper.record_fingerprint(rec)
        return s

    # ------------------------------------------------------------------
    def read_output(self):
        """Read back the corpus (all shards or single file) as a list."""
        paths = []
        sp = os.path.join(self.cfg.out_dir, "corpus.jsonl")
        if os.path.exists(sp):
            paths.append(sp)
        elif os.path.isdir(self.cfg.out_dir):
            for p in sorted(os.listdir(self.cfg.out_dir)):
                if p.startswith("corpus-") and p.endswith(".jsonl"):
                    paths.append(os.path.join(self.cfg.out_dir, p))
        out = []
        for p in paths:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        out.append(json.loads(line))
        return out
