"""Batched extraction: DB rows + on-disk artifact index.

Read-only. Walks downloads/ and downloads/cleaned/ to build a
stem -> {relpath: abspath} index, then drives the mapper over the
sessions table in id-ordered batches (mission §4.14: batched
extraction; no full-table materialization of big text columns happens
in one query — llm_output is batched too).
"""

import os
import time

from . import database as _database


AUDIO_EXTS = (".mp3", ".mp4")
TEXT_EXTS = (".srt", ".txt", ".json")


class DiskIndex(object):
    """Maps stems to on-disk artifact paths (relative + absolute)."""

    def __init__(self, downloads_dir):
        self.downloads_dir = downloads_dir
        self.by_stem = {}   # stem -> {kind: relpath}
        self.by_relpath = {}  # relpath -> abspath
        self.scanned_at = None
        self.counts = {"files": 0, "stems": 0, "errors": 0}

    def _scan_dir(self, rel_dir, base_abs):
        if not os.path.isdir(base_abs):
            return
        try:
            names = os.listdir(base_abs)
        except OSError:
            self.counts["errors"] += 1
            return
        for name in names:
            ext = os.path.splitext(name)[1].lower()
            if ext not in AUDIO_EXTS + TEXT_EXTS:
                continue
            abspath = os.path.join(base_abs, name)
            if not os.path.isfile(abspath):
                continue
            relpath = (rel_dir + "/" + name).replace(os.sep, "/")
            self.by_relpath[relpath] = abspath
            stem = os.path.splitext(name)[0]
            slot = self.by_stem.setdefault(stem, {})
            slot.setdefault(relpath, abspath)
            self.counts["files"] += 1

    def scan(self):
        self.scanned_at = time.time()
        self._scan_dir("downloads", self.downloads_dir)
        self._scan_dir("downloads/cleaned", os.path.join(self.downloads_dir, "cleaned"))
        self.counts["stems"] = len(self.by_stem)
        return self

    def find(self, relpath):
        """abspath for a server-relative path (downloads/...), or None."""
        return self.by_relpath.get(relpath)

    def stem_map(self, stem):
        return self.by_stem.get(stem, {})


class Extractor(object):
    def __init__(self, db, cfg, disk=None):
        self.db = db
        self.cfg = cfg
        if disk is None:
            # DiskIndex expects a directory that CONTAINS downloads/ (it
            # scans <base>/downloads and <base>/downloads/cleaned); in
            # production that is the project ROOT. cfg.downloads_dir is
            # already <root>/downloads, so it cannot be the base itself.
            base = getattr(cfg, "root", None) or os.path.dirname(cfg.downloads_dir or "")
            disk = DiskIndex(os.path.join(base, "downloads")).scan()
        self.disk = disk

    # ------------------------------------------------------------------
    def load_programs(self):
        rows = self.db.fetch_programs()
        by_id = {}
        by_chm = {}
        for r in rows:
            by_id[r["id"]] = r
            ch = _database.Database.parse_ch(r.get("url"))
            m = _database.Database.parse_m(r.get("url"))
            if ch is not None and m is not None:
                by_chm.setdefault((ch, m), []).append(r["id"])
        return by_id, by_chm

    def load_llm_outputs(self):
        """session_id -> [rows] (all job types/models, order by id)."""
        total, gen = self.db.fetch_llm_outputs()
        by_session = {}
        n = 0
        for r in gen:
            by_session.setdefault(r["session_id"], []).append(r)
            n += 1
        return by_session, n

    def load_asr_outputs(self):
        by_session = {}
        for r in self.db.fetch_asr_outputs():
            by_session.setdefault(r["session_id"], []).append(r)
        return by_session

    def load_crop_detections(self):
        out = {}
        for r in self.db.fetch_crop_detections():
            out[r["session_id"]] = r
        return out

    # ------------------------------------------------------------------
    def iter_sessions(self, where=None, params=None):
        """Yield (total, session_row) pairs in id order, batched."""
        return self.db.fetch_sessions(where=where, params=params)
