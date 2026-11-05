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

    def _run_inner(self, staging, where, params, limit, run_id, exported_at,
                   deterministic, t0):
        # ---- load lookup tables (small) -----------------------------
        prog_by_id, prog_by_chm = self.ex.load_programs()
        llm_by_session, llm_total = self.ex.load_llm_outputs()
        asr_by_session = self.ex.load_asr_outputs()
        crop_by_session = self.ex.load_crop_detections()
        counts = self.db.table_counts()
        wm = self.db.high_watermark()
        if deterministic:
            # keep data fields reproducible; the DB watermark is the anchor
            wm = dict(wm)
            wm["note"] = ("frozen: deterministic build pinned to DB "
                          "high watermark")

        # ---- walk sessions ------------------------------------------
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

        # ---- staged corpus files -------------------------------------
        stage_files = {
            "corpus": out_path if out_path else shard_paths,
            "invalid": invalid_path if os.path.exists(invalid_path) else None,
            "quarantine": quarantine_path if os.path.exists(quarantine_path) else None,
        }

        # ---- manifest + stats (staged) -------------------------------
        scanned_at = self.ex.disk.scanned_at
        if deterministic:
            # wall-clock epoch float -> keep data fields reproducible
            scanned_at = "frozen: pinned to run's disk scan (deterministic)"
        manifest = {
            "schema_version": "1.0",
            "run_id": run_id,
            "exported_at": exported_at,
            "mode": "incremental" if where else "full",
            "deterministic": deterministic,
            "records_written": n_ok,
            "records_invalid": n_invalid,
            "records_quarantined": n_quarantine,
            "sessions_seen": n,
            "sessions_total_in_db": total_sessions,
            "output_files": ([os.path.join(self.cfg.out_dir, "corpus.jsonl")]
                             if out_path
                             else [os.path.join(self.cfg.out_dir, "corpus-%04d.jsonl" % (i + 1))
                                   for i in range(len(shard_paths))]),
            "shard_lines": self.cfg.shard_lines,
            "quarantine_file": "quarantine.jsonl" if stage_files["quarantine"] else None,
            "invalid_file": "invalid.jsonl" if stage_files["invalid"] else None,
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
        _atomic_write(os.path.join(staging, "manifest.json"),
                      json.dumps(manifest, indent=2, ensure_ascii=False))
        _atomic_write(os.path.join(staging, "stats.json"),
                      json.dumps(stats, indent=2, ensure_ascii=False))

        # ---- validate staged output, archive live, promote ------------
        self._validate_staged(stage_files, n_ok, n_invalid, n_quarantine)
        prev_slot = self._archive_live()
        manifest["previous_export"] = (
            None if prev_slot is None
            else "previous/" + prev_slot)
        manifest["duration_sec"] = round(time.time() - t0, 1)
        _atomic_write(os.path.join(staging, "manifest.json"),
                      json.dumps(manifest, indent=2, ensure_ascii=False))
        self._promote(staging)

        # ---- checksums over the promoted (live) data files ------------
        manifest["checksums_files"] = self._write_checksums()
        self._prune_previous()

        self.log("exporter: done in %ss — %d ok, %d invalid, %d quarantined, "
                 "%d seen (total %d)"
                 % (manifest["duration_sec"], n_ok, n_invalid, n_quarantine,
                    n, total_sessions))
        return manifest

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
