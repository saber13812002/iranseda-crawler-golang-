"""Exporter: orchestrates DB + disk -> corpus.jsonl + manifest + stats.

Writes (all under cfg.out_dir):
  corpus.jsonl            (or corpus-0001.jsonl... when sharded)
  manifest.json           (counts, watermark, config, fingerprints)
  stats.json              (per-status / per-job-type / disk-join stats)
  invalid.jsonl           (records that failed validation — never dropped
                           silently; kept for repair)

Idempotency (mission §5): output is keyed by record_id; re-running with
the same DB state produces byte-identical corpus content (exported_at is
kept out of the fingerprint). Writes are atomic (tmp file + os.replace).
"""

import os
import time
import json
import datetime

from . import database as _db
from . import extractor as _extractor
from . import mapper as _mapper
from . import validator as _validator


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


class Exporter(object):
    def __init__(self, db, cfg, disk=None, log=print):
        self.db = db
        self.cfg = cfg
        self.log = log
        self.ex = _extractor.Extractor(db, cfg, disk=disk)

    # ------------------------------------------------------------------
    def run(self, where=None, params=None, limit=None, run_id=None):
        """Full (or filtered) export. Returns the manifest dict."""
        t0 = time.time()
        exported_at = _now_iso()
        if run_id is None:
            run_id = "corpus-%s" % datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

        os.makedirs(self.cfg.out_dir, exist_ok=True)

        # ---- load lookup tables (small) -----------------------------
        prog_by_id, prog_by_chm = self.ex.load_programs()
        llm_by_session, llm_total = self.ex.load_llm_outputs()
        asr_by_session = self.ex.load_asr_outputs()
        crop_by_session = self.ex.load_crop_detections()
        counts = self.db.table_counts()
        wm = self.db.high_watermark()

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
        invalid_path = os.path.join(self.cfg.out_dir, "invalid.jsonl")
        inv = None
        seen_ids = set()
        fingerprints = {}
        stats = self._init_stats()

        shard_size = self.cfg.shard_lines
        if shard_size > 0:
            def new_shard():
                global_idx = len(shard_paths)
                p = os.path.join(self.cfg.out_dir, "corpus-%04d.jsonl" % (global_idx + 1))
                shard_paths.append(p)
                return open(p, "w", encoding="utf-8", newline="\n")
            f = new_shard()
            shard_count_in_file = 0
        else:
            out_path = os.path.join(self.cfg.out_dir, "corpus.jsonl")
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
                    n_invalid += 1
                    if inv is None:
                        inv = open(invalid_path, "w", encoding="utf-8", newline="\n")
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

        # ---- manifest + stats ----------------------------------------
        manifest = {
            "schema_version": "1.0",
            "run_id": run_id,
            "exported_at": exported_at,
            "mode": "incremental" if where else "full",
            "records_written": n_ok,
            "records_invalid": n_invalid,
            "sessions_seen": n,
            "sessions_total_in_db": total_sessions,
            "output_files": ([out_path] if out_path else [p for p in shard_paths]),
            "shard_lines": self.cfg.shard_lines,
            "db_counts_at_run": counts,
            "watermark": wm,
            "disk": {
                "scanned_at": self.ex.disk.scanned_at,
                "files_indexed": self.ex.disk.counts["files"],
                "stems_indexed": self.ex.disk.counts["stems"],
                "scan_errors": self.ex.disk.counts["errors"],
            },
            "config": self.cfg.to_dict(),
            "duration_sec": round(time.time() - t0, 1),
            "fingerprint_note": "per-record fingerprints in stats.fingerprints_sample",
        }
        _atomic_write(os.path.join(self.cfg.out_dir, "manifest.json"),
                      json.dumps(manifest, indent=2, ensure_ascii=False))
        _atomic_write(os.path.join(self.cfg.out_dir, "stats.json"),
                      json.dumps(stats, indent=2, ensure_ascii=False))

        self.log("exporter: done in %ss — %d ok, %d invalid, %d seen (total %d)"
                 % (manifest["duration_sec"], n_ok, n_invalid, n, total_sessions))
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
        else:
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
