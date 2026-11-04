"""End-to-end export with a fake read-only DB (no network)."""

import datetime
import json
import os
import tempfile

from corpus import exporter as E
from corpus import mapper as M


SRT = "1\n00:00:00,000 --> 00:00:10,000\nسلام\n\n2\n00:00:10,000 --> 00:00:20,000\nدنیا\n"
CORR = "1\n0:00:00 --> 0:00:20\nسلام و دنیا\n"


class FakeDB(object):
    def __init__(self, sessions, programs, llm, disk_dir=None):
        self.sessions = sessions
        self.programs = programs
        self.llm = llm

    def ping(self):
        return "5.5.5-fake"

    def table_counts(self):
        return {"radio_programs": len(self.programs),
                "radio_program_sessions": len(self.sessions),
                "llm_output": len(self.llm), "asr_output": 0,
                "crop_detection": 0}

    def high_watermark(self):
        return {"sessions_updated_at": "2026-01-06 12:00:00",
                "sessions_max_id": max(s["id"] for s in self.sessions),
                "llm_finished_at": "2026-01-06 10:05:00",
                "llm_max_id": 901}

    def watermark_clause(self, wm, overlap_sec):
        return "1=1", []

    def fetch_programs(self):
        return list(self.programs)

    def fetch_sessions(self, batch_size=1000, where=None, params=None):
        rows = sorted(self.sessions, key=lambda s: s["id"])
        return len(rows), iter(rows)

    def fetch_llm_outputs(self, session_ids=None, where=None, params=None):
        rows = list(self.llm)
        return len(rows), iter(rows)

    def fetch_asr_outputs(self, session_ids=None):
        return []

    def fetch_crop_detections(self, session_ids=None):
        return []


def _session(i, pid=11, link=None, filename=None, srt=None):
    return {
        "id": i,
        "program_id": pid,
        "link": link or ("../epgarchivePart/?VALID=TRUE&ch=14&e=%d" % (10000000 + i)),
        "created_at": datetime.datetime(2024, 11, 8, 0, 0, 0),
        "updated_at": datetime.datetime(2026, 1, 6, 12, 0, 0),
        "filename": filename,
        "srt_filename": srt,
        "is_downloaded": 1,
        "status": "subtitled",
        "is_subtitled": 1,
        "attempts": 1,
        "last_error": None,
    }


def _program(pid=11):
    return {
        "id": pid,
        "name": "برنامه",
        "url": "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=044116",
        "time": datetime.time(9, 0, 0),
        "time_description": None,
        "description": None,
        "created_at": datetime.datetime(2024, 11, 8, 0, 0, 0),
        "start": None, "radio": "معارف", "radio_id": None,
        "is_legacy": 0, "legacy_expires_at": None,
        "crop_offset": None, "crop_enabled": None, "crop_auto": None,
    }


def _llm(i, jt, content=None, srt=None, rel=None):
    return {
        "id": i, "session_id": 1, "job_type": jt,
        "model": "qwen38-nothinking", "prompt_id": 1, "job_id": None,
        "content": content, "content_en": None, "srt_content": srt,
        "file_relpath": rel,
        "started_at": datetime.datetime(2026, 1, 6, 10, 0, 0),
        "finished_at": datetime.datetime(2026, 1, 6, 10, 5, 0),
        "status": "done", "error": None,
        "input_tokens": 1, "output_tokens": 1,
    }


def _setup(tmp, n_sessions=3, with_artifacts=True):
    downloads = os.path.join(tmp, "downloads")
    os.makedirs(os.path.join(downloads, "cleaned"), exist_ok=True)
    sessions = []
    for i in range(1, n_sessions + 1):
        stem = "radio-maaref-05-01-%02d-09-00" % i
        if with_artifacts:
            with open(os.path.join(downloads, "cleaned", stem + ".srt"),
                      "w", encoding="utf-8") as f:
                f.write(SRT)
            with open(os.path.join(downloads, "cleaned", stem + ".txt"),
                      "w", encoding="utf-8") as f:
                f.write("سلام\n")
            with open(os.path.join(downloads, stem + ".mp3"), "wb") as f:
                f.write(b"0")
        sessions.append(_session(i, filename=stem + ".mp3", srt=stem + ".srt"))
    # one session without a filename (broadcast null)
    sessions.append(_session(99, filename=None, srt=None))
    llm = [_llm(900, "correct_subtitles", srt=CORR,
                rel="downloads/cleaned/radio-maaref-05-01-01-09-00.correct.srt"),
           _llm(901, "summary", content="خلاصه: برنامه صبح",
                rel="downloads/cleaned/radio-maaref-05-01-01-09-00.summary.txt")]
    prog = [_program()]
    db = FakeDB(sessions, prog, llm)

    class Cfg(object):
        root = tmp
        downloads_dir = downloads
        out_dir = os.path.join(tmp, "out")
        db_host = "x"
        db_port = 1
        db_user = "u"
        db_pass = "p"
        db_name = "d"
        inline_originals = True
        inline_llm = True
        shard_lines = 0
        incremental_hours = 6.0
        overlap_hours = 12.0
        export_enabled = False
        site_base = "https://radio.iranseda.ir/"

        def to_dict(self):
            return {
                "root": self.root, "downloads_dir": self.downloads_dir,
                "out_dir": self.out_dir, "db_host": self.db_host,
                "db_port": self.db_port, "db_user": self.db_user,
                "db_name": self.db_name, "db_pass": "<redacted>",
                "inline_originals": self.inline_originals,
                "inline_llm": self.inline_llm, "shard_lines": self.shard_lines,
                "incremental_hours": self.incremental_hours,
                "overlap_hours": self.overlap_hours,
                "export_enabled": self.export_enabled,
                "site_base": self.site_base,
            }
    return db, Cfg(), sessions


def test_full_export_writes_corpus_manifest_stats():
    with tempfile.TemporaryDirectory() as tmp:
        db, cfg, sessions = _setup(tmp)
        ex = E.Exporter(db, cfg, log=lambda m: None)
        manifest = ex.run()
        out = os.path.join(cfg.out_dir, "corpus.jsonl")
        assert os.path.exists(out)
        assert os.path.exists(os.path.join(cfg.out_dir, "manifest.json"))
        assert os.path.exists(os.path.join(cfg.out_dir, "stats.json"))
        assert manifest["records_written"] == len(sessions)
        assert manifest["records_invalid"] == 0
        with open(out, encoding="utf-8") as f:
            recs = [json.loads(l) for l in f if l.strip()]
        assert len(recs) == len(sessions)
        ids = [r["record_id"] for r in recs]
        assert len(set(ids)) == len(ids)
        no_filename = [r for r in recs
                       if r["database_refs"]["session_id"] == 99][0]
        assert no_filename["broadcast"] is None
        assert "broadcast.date" in no_filename["quality"]["missing"]


def test_export_limit():
    with tempfile.TemporaryDirectory() as tmp:
        db, cfg, _ = _setup(tmp)
        ex = E.Exporter(db, cfg, log=lambda m: None)
        manifest = ex.run(limit=2)
        assert manifest["records_written"] == 2
        assert manifest["sessions_seen"] == 2


def test_export_invalid_goes_to_invalid_jsonl():
    with tempfile.TemporaryDirectory() as tmp:
        db, cfg, sessions = _setup(tmp)
        # no ch/e in the link + no program id -> fallback record_id cannot
        # be built from digits -> record_id validation failure
        bad = _session(500, pid=None, link="weird-link-no-params")
        db.sessions = sessions + [bad]
        ex = E.Exporter(db, cfg, log=lambda m: None)
        manifest = ex.run()
        assert manifest["records_invalid"] == 1
        inv = os.path.join(cfg.out_dir, "invalid.jsonl")
        assert os.path.exists(inv)
        with open(inv, encoding="utf-8") as f:
            row = json.loads(f.readline())
        assert any("record_id" in p for p in row["problems"])


def test_new_run_removes_stale_previous_outputs():
    # 2026-11-04 pilot: a 100-invalid run left invalid.jsonl + (when sharded)
    # stale corpus-NNNN.jsonl shards behind; a fresh run must remove them so
    # the next run's results cannot be misread.
    with tempfile.TemporaryDirectory() as tmp:
        db, cfg, _ = _setup(tmp)
        os.makedirs(cfg.out_dir, exist_ok=True)
        stale_invalid = os.path.join(cfg.out_dir, "invalid.jsonl")
        stale_shard = os.path.join(cfg.out_dir, "corpus-0001.jsonl")
        with open(stale_invalid, "w", encoding="utf-8") as f:
            f.write('{"stale": true}\n')
        with open(stale_shard, "w", encoding="utf-8") as f:
            f.write('{"stale": true}\n')
        cfg.shard_lines = 2
        ex = E.Exporter(db, cfg, log=lambda m: None)
        manifest = ex.run()
        assert manifest["records_invalid"] == 0
        assert not os.path.exists(stale_invalid), "stale invalid.jsonl must be removed"
        shards = [p for p in os.listdir(cfg.out_dir)
                  if p.startswith("corpus-") and p.endswith(".jsonl")]
        total = 0
        for name in shards:
            with open(os.path.join(cfg.out_dir, name), encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        total += 1
                        assert '"stale"' not in line
        assert total == manifest["records_written"]


def test_export_idempotent_fingerprints():
    with tempfile.TemporaryDirectory() as tmp:
        db, cfg, _ = _setup(tmp)
        ex1 = E.Exporter(db, cfg, log=lambda m: None)
        m1 = ex1.run(run_id="run-A")
        recs1 = ex1.read_output()
        fp1 = {r["record_id"]: M.record_fingerprint(r) for r in recs1}
        ex2 = E.Exporter(db, cfg, log=lambda m: None)
        m2 = ex2.run(run_id="run-B")
        recs2 = ex2.read_output()
        fp2 = {r["record_id"]: M.record_fingerprint(r) for r in recs2}
        assert fp1 == fp2
        assert m1["records_written"] == m2["records_written"]


def test_sharding():
    with tempfile.TemporaryDirectory() as tmp:
        db, cfg, _ = _setup(tmp, n_sessions=4)
        cfg.shard_lines = 3
        ex = E.Exporter(db, cfg, log=lambda m: None)
        manifest = ex.run()
        files = manifest["output_files"]
        assert len(files) == 2
        total = 0
        for p in files:
            with open(p, encoding="utf-8") as f:
                total += sum(1 for l in f if l.strip())
        assert total == manifest["records_written"]


def test_stats_counters():
    with tempfile.TemporaryDirectory() as tmp:
        db, cfg, sessions = _setup(tmp)
        ex = E.Exporter(db, cfg, log=lambda m: None)
        ex.run()
        with open(os.path.join(cfg.out_dir, "stats.json"), encoding="utf-8") as f:
            stats = json.load(f)
        assert stats["records_with_original_srt"] >= 3
        assert stats["records_with_corrected_srt"] == 1
        assert stats["records_with_summary"] == 1
        assert stats["episode_key_link"] == len(sessions)
        assert stats["by_status"]["subtitled"] == len(sessions)
