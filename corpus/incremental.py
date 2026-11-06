"""Incremental export + reconciliation (mission §8).

Watermark model (schema ambiguity #11: llm_output has no updated_at):
  * sessions:  updated_at + max(id)  with an overlap window
  * llm_output: finished_at + max(id) with an overlap window
Overlap re-processes recently-touched rows; merging is by record_id, so
re-exports are idempotent (corrections update the SAME record; nothing is
ever deleted physically — a session that disappears from the DB is
recorded in the reconcile report, not removed from history).

Usage (from cli.py):
  python -m corpus.cli incremental        # watermark-based partial export
  python -m corpus.cli reconcile          # full re-scan + diff report
"""

import os
import json
import time
import datetime


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(data)
    os.replace(tmp, path)


class IncrementalExporter(object):
    def __init__(self, exporter):
        self.ex = exporter  # a corpus.exporter.Exporter
        self.cfg = exporter.cfg
        self.db = exporter.db

    # ------------------------------------------------------------------
    def _load_state(self):
        p = os.path.join(self.cfg.out_dir, "incremental_state.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        return None

    def _save_state(self, wm, manifest):
        os.makedirs(self.cfg.out_dir, exist_ok=True)
        state = {
            "updated_at": _now_iso(),
            "watermark": wm,
            "last_run_id": manifest.get("run_id"),
            "last_records_written": manifest.get("records_written"),
        }
        _atomic_write(os.path.join(self.cfg.out_dir, "incremental_state.json"),
                      json.dumps(state, indent=2, ensure_ascii=False))

    # ------------------------------------------------------------------
    def run(self, force_full=False, run_id=None, exported_at=None,
            linkage_ctx=None):
        """One incremental cycle. Returns the manifest.

        Stage 4: the watermark run is an upsert-MERGE against the live
        corpus (exporter merge mode). run_id / exported_at can be pinned
        to the live manifest (cli --pin) so that a no-change merge is a
        byte-identical no-op (records embed provenance.exported_at and
        provenance.export_version=run_id).
        """
        state = self._load_state()
        overlap_sec = int(self.cfg.overlap_hours * 3600)
        if force_full or state is None or not state.get("watermark"):
            self.ex.log("incremental: no prior watermark — running FULL export")
            manifest = self.ex.run(run_id=run_id, exported_at=exported_at,
                                   linkage_ctx=linkage_ctx)
        else:
            wm = state["watermark"]
            clause, params = self.db.watermark_clause(wm, overlap_sec)
            self.ex.log("incremental: WHERE %s params=%s" % (clause, params))
            manifest = self.ex.run(where=clause, params=params,
                                   run_id=run_id, exported_at=exported_at,
                                   linkage_ctx=linkage_ctx)
        wm_after = self.db.high_watermark()
        self._save_state(wm_after, manifest)
        return manifest

    # ------------------------------------------------------------------
    def reconcile(self):
        """Full re-scan + diff against the previous full output.

        Writes reconcile_report.json:
          added / removed / changed (by fingerprint) / unchanged counts.
        Deletions are RECORDS in the report (never physical removals).
        """
        t0 = time.time()
        # fingerprint the existing output first
        old = {}
        for rec in self.ex.read_output():
            old[rec["record_id"]] = _fingerprint(rec)
        # full export (overwrites corpus output atomically per file)
        manifest = self.ex.run()
        new = {}
        for rec in self.ex.read_output():
            new[rec["record_id"]] = _fingerprint(rec)

        added = sorted(set(new) - set(old))
        removed = sorted(set(old) - set(new))
        changed = sorted(rid for rid in set(new) & set(old) if new[rid] != old[rid])
        unchanged = len(set(new) & set(old)) - len(changed)

        report = {
            "reconciled_at": _now_iso(),
            "duration_sec": round(time.time() - t0, 1),
            "previous_records": len(old),
            "current_records": len(new),
            "added": added,
            "removed": removed,
            "changed": changed,
            "unchanged": unchanged,
            "note": "removed/added/changed are recorded here; corpus history is never physically deleted",
        }
        _atomic_write(os.path.join(self.cfg.out_dir, "reconcile_report.json"),
                      json.dumps(report, indent=2, ensure_ascii=False))
        self.ex.log("reconcile: +%d -%d ~%d =%d in %ss"
                       % (len(added), len(removed), len(changed), unchanged,
                          report["duration_sec"]))
        return report


def _fingerprint(rec):
    from . import mapper
    return mapper.record_fingerprint(rec)
