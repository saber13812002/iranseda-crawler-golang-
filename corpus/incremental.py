"""Incremental export + reconciliation (mission §8 — Stage 4).

Merge semantics (Stage 4): a cycle NEVER replaces the live corpus with
only the changed slice. It (1) detects the changed sessions using the
union of all available freshness signals, (2) exports just that slice,
and (3) MERGES it into the currently-live corpus by record_id
(Exporter.run_incremental). Corrections update the SAME record;
cross-run record_id collisions go to quarantine (first-seen wins;
Class B policy: permanent quarantine until identity is proven).

Change detection (strongest available — db.changed_session_ids):
  * sessions.updated_at >= watermark - overlap  (touch)
  * sessions.id > watermark.max_id              (inserts)
  * llm_output.finished_at >= wm - overlap / id (new SRT / correction —
    corrections do NOT bump the session's updated_at)
  * asr_output.updated_at >= wm - overlap
  * crop_detection.updated_at >= wm - overlap
plus a DISK signature (file count + max mtime of the downloads tree):
  * disk changed but detection found nothing -> FULL export fallback
    (safe recovery; the disk can change ahead of the DB)
  * DB watermark + disk unchanged -> idempotent SKIP (no live rewrite,
    no churn)

Boundedness: if the changed-session count exceeds
cfg.max_incremental_sessions the cycle loudly falls back to a FULL
export (outage safety: a backlogged watermark must not produce a
silent partial corpus).

Failure recovery: state (watermark + disk signature) is saved ONLY
after a successful promote; a failed cycle re-detects from the same
watermark next time, and a missing/corrupt live output forces a full
rebuild. The exclusive export.lock (exporter module) guarantees one
export at a time across CLI/scheduler invocations.

Nothing is ever physically deleted: a session that disappears from the
DB stays in the corpus; the weekly reconcile records such removals in
reconcile_report.json.

Usage (from cli.py):
  python -m corpus.cli incremental        # merge-based incremental cycle
  python -m corpus.cli incremental --full # force a full rebuild
  python -m corpus.cli reconcile          # full re-scan + diff report
"""

import os
import json
import time
import datetime

from .exporter import NoLiveCorpusError


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _atomic_write(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
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
    # state
    # ------------------------------------------------------------------
    def _load_state(self):
        p = os.path.join(self.cfg.out_dir, "incremental_state.json")
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except (ValueError, OSError):
                return None  # corrupt state -> full rebuild next cycle
        return None

    def _save_state(self, wm, manifest=None, disk_sig=None, action=None,
                    extra=None):
        os.makedirs(self.cfg.out_dir, exist_ok=True)
        prev = self._load_state() or {}
        state = {
            "updated_at": _now_iso(),
            "watermark": wm,
            "disk_signature": disk_sig,
            "last_action": action or ("export" if manifest else None),
            "last_run_id": prev.get("last_run_id"),
            "last_records_written": prev.get("last_records_written"),
            "last_skip_at": prev.get("last_skip_at"),
        }
        if manifest is not None:
            state["last_run_id"] = manifest.get("run_id")
            state["last_records_written"] = manifest.get("records_written")
        if extra:
            state.update(extra)
        _atomic_write(os.path.join(self.cfg.out_dir, "incremental_state.json"),
                      json.dumps(state, indent=2, ensure_ascii=False))

    # ------------------------------------------------------------------
    # disk signature
    # ------------------------------------------------------------------
    def disk_signature(self):
        """(file_count, max_mtime_int) over the downloads tree, or None
        when the tree does not exist. Cheap (os.walk) and stable: it
        detects NEW on-disk artifacts (SRTs, audio) that may precede the
        DB update."""
        base = self.cfg.downloads_dir
        if not base or not os.path.isdir(base):
            return None
        n = 0
        mt = 0
        for _dirpath, _dirnames, filenames in os.walk(base):
            for name in filenames:
                p = os.path.join(_dirpath, name)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                n += 1
                if st.st_mtime > mt:
                    mt = st.st_mtime
        return [n, int(mt)]

    # ------------------------------------------------------------------
    # the cycle
    # ------------------------------------------------------------------
    def run(self, force_full=False):
        """One incremental cycle. Returns the manifest (or a skip dict)."""
        state = self._load_state()
        overlap_sec = int(self.cfg.overlap_hours * 3600)
        cap = int(getattr(self.cfg, "max_incremental_sessions", 10000))

        wm_now = self.db.high_watermark()
        disk_now = self.disk_signature()

        # ---- 1) no prior watermark -> full build ----------------------
        if force_full or state is None or not state.get("watermark"):
            self.ex.log("incremental: no prior watermark%s — running FULL "
                        "export" % (" (forced)" if force_full else ""))
            manifest = self.ex.run()
            self._save_state(self.db.high_watermark(), manifest,
                             disk_sig=self.disk_signature(), action="full")
            return manifest

        wm = state["watermark"]
        disk_prev = state.get("disk_signature")
        has_live = bool(self.ex.read_output())

        # ---- 2) idempotent no-change fast path ------------------------
        # identical DB watermark AND identical disk signature: nothing
        # new; do NOT rewrite the live export (no churn, stable bytes).
        # A skip is only ever returned when a live corpus exists —
        # otherwise the next cycle would have nothing to merge into.
        if has_live and wm_now == wm and disk_now == disk_prev:
            self.ex.log("incremental: no changes (watermark + disk "
                        "signature unchanged) — skipping export")
            self._save_state(wm_now, disk_sig=disk_now, action="skip",
                             extra={"last_skip_at": _now_iso()})
            return {"skipped": True, "reason": "no changes detected",
                    "watermark": wm_now, "run_id": state.get("last_run_id")}
        if not has_live:
            self.ex.log("incremental: no live corpus to merge into — "
                        "running FULL export")
            manifest = self.ex.run()
            self._save_state(self.db.high_watermark(), manifest,
                             disk_sig=self.disk_signature(), action="full")
            return manifest

        # ---- 3) detect changed sessions (union of signals) -----------
        ids, signals = self.db.changed_session_ids(wm, overlap_sec)
        disk_changed = (disk_prev is None or disk_now != disk_prev)
        wm_changed = (wm_now != wm)

        # disk changed but DB detection found nothing (or detection
        # itself failed): a silent partial merge is not acceptable —
        # fall back to a full rebuild.
        if not ids:
            if wm_changed or disk_changed:
                self.ex.log("incremental: signals changed "
                            "(wm_changed=%s, disk_changed=%s) but no "
                            "changed sessions detected — falling back to "
                            "FULL export" % (wm_changed, disk_changed))
                manifest = self.ex.run()
                self._save_state(self.db.high_watermark(), manifest,
                                 disk_sig=self.disk_signature(), action="full")
                return manifest
            # belt and braces: nothing changed at all
            self._save_state(wm_now, disk_sig=disk_now, action="skip",
                             extra={"last_skip_at": _now_iso()})
            return {"skipped": True, "reason": "no changes detected",
                    "watermark": wm_now, "run_id": state.get("last_run_id")}

        # ---- 4) boundedness: too many changed sessions -> full -------
        if len(ids) > cap:
            self.ex.log("incremental: %d changed sessions exceed cap %d — "
                        "falling back to FULL export" % (len(ids), cap))
            manifest = self.ex.run()
            self._save_state(self.db.high_watermark(), manifest,
                             disk_sig=self.disk_signature(), action="full")
            return manifest

        # ---- 5) merge the slice into the live corpus ------------------
        where = "id IN (%s)" % ",".join(str(int(i)) for i in ids)
        extra = {
            "change_detection": {
                "signals": signals,
                "changed_session_count": len(ids),
                "changed_session_ids": ids,
                "stored_watermark": wm,
                "watermark_now": wm_now,
                "disk_changed": disk_changed,
            },
        }
        try:
            manifest = self.ex.run_incremental(where=where, extra=extra)
        except NoLiveCorpusError:
            self.ex.log("incremental: no live corpus to merge into — "
                        "running FULL export")
            manifest = self.ex.run()
            self._save_state(self.db.high_watermark(), manifest,
                             disk_sig=self.disk_signature(), action="full")
            return manifest
        self._save_state(self.db.high_watermark(), manifest,
                         disk_sig=self.disk_signature(),
                         action="incremental")
        return manifest

    # ------------------------------------------------------------------
    def reconcile(self):
        """Full re-scan + diff against the previous full output.

        Writes reconcile_report.json:
          added / removed / changed (by fingerprint) / unchanged counts.
        Deletions are RECORDS in the report (never physical removals).
        Also refreshes the incremental state (watermark + disk sig).
        """
        t0 = time.time()
        # fingerprint the existing output first
        old = {}
        for rec in self.ex.read_output():
            old[rec["record_id"]] = _fingerprint(rec)
        # full export (atomically promoted per file)
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
        self._save_state(self.db.high_watermark(), manifest,
                         disk_sig=self.disk_signature(), action="reconcile")
        self.ex.log("reconcile: +%d -%d ~%d =%d in %ss"
                        % (len(added), len(removed), len(changed), unchanged,
                           report["duration_sec"]))
        return report


def _fingerprint(rec):
    from . import mapper
    return mapper.record_fingerprint(rec)
