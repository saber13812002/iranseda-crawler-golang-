"""Stage 4 — idempotent incremental export + reconciliation (no network).

Mission acceptance: a full rebuild vs an incremental merge on the SAME
snapshot produce equivalent logical datasets (record_id -> fingerprint
sets equal, quarantine sets equal). Plus: no-change idempotent skip,
corrections updating the same record, bounded fallback, exclusive job
lock, and failure recovery.

Fixtures reuse tests/corpus/test_exporter.py (FakeDB + _setup) and
extend FakeDB with:
  * fetch_sessions honoring `id IN (...)` WHERE clauses
  * db.changed_session_ids() (the multi-signal union detector)
  * mutable llm rows (to simulate corrections)
"""

import datetime
import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from corpus import exporter as E
from corpus import incremental as I
from corpus import mapper as M

from test_exporter import SRT, _session, _program, _llm, _setup


class IncDB(object):
    """Wraps the test_exporter FakeDB and adds change detection."""

    def __init__(self, inner):
        self._inner = inner

    # pass-throughs -----------------------------------------------------
    def ping(self):
        return self._inner.ping()

    def table_counts(self):
        return self._inner.table_counts()

    def high_watermark(self):
        # DYNAMIC watermark: reflects the current fixture rows, so a
        # newly appended llm_output row advances the watermark (like the
        # real DB). The original FakeDB pins "2026-01-06 12:00:00",
        # which is exactly the fixture's max updated_at.
        s = self._inner.sessions
        max_s = max((x["updated_at"] for x in s), default=None)
        l = self._inner.llm
        max_f = max((x["finished_at"] for x in l), default=None)
        return {"sessions_updated_at": (max_s.isoformat()
                                         if max_s else None),
                "sessions_max_id": max((x["id"] for x in s), default=0),
                "llm_finished_at": (max_f.isoformat() if max_f else None),
                "llm_max_id": max((x["id"] for x in l), default=0)}

    def watermark_clause(self, wm, overlap_sec):
        return self._inner.watermark_clause(wm, overlap_sec)

    def fetch_programs(self):
        return self._inner.fetch_programs()

    def fetch_llm_outputs(self, session_ids=None, where=None, params=None):
        return self._inner.fetch_llm_outputs(
            session_ids=session_ids, where=where, params=params)

    def fetch_asr_outputs(self, session_ids=None):
        return self._inner.fetch_asr_outputs(session_ids=session_ids)

    def fetch_crop_detections(self, session_ids=None):
        return self._inner.fetch_crop_detections(session_ids=session_ids)

    def fetch_sessions(self, batch_size=1000, where=None, params=None):
        rows = sorted(self._inner.sessions, key=lambda s: s["id"])
        # honor "id IN (a, b, c)" (the only WHERE the incremental path
        # emits); "1=1" / watermark clauses pass everything through.
        ids = set(int(x) for x in (where or "").replace("id IN (", "")
                  .replace(")", "").split(",") if x.strip())
        if where and "id IN (" in where:
            rows = [r for r in rows if r["id"] in ids]
        return len(rows), iter(rows)

    # the multi-signal detector (duck of corpus.database) ---------------
    def changed_session_ids(self, wm, overlap_sec):
        from datetime import timedelta
        changed = set()

        def since(key):
            ts = (wm.get(key) or "")[:19]
            if not ts:
                return None
            return (datetime.datetime.fromisoformat(ts)
                    - datetime.timedelta(seconds=int(overlap_sec)))

        # sessions: touch (updated_at >= wm - overlap) or insert
        s_since = since("sessions_updated_at")
        for s in self._inner.sessions:
            ua = s.get("updated_at")
            if ua is None or (s_since is not None and ua >= s_since):
                changed.add(int(s["id"]))
            if s["id"] > (wm.get("sessions_max_id") or 0):
                changed.add(int(s["id"]))
        # llm_output: finished_at >= wm - overlap or id > wm max id
        l_since = since("llm_finished_at")
        for lo in self._inner.llm:
            if lo.get("session_id") is None:
                continue
            fa = lo.get("finished_at")
            if fa is not None and (l_since is not None and fa >= l_since):
                changed.add(int(lo["session_id"]))
            if lo["id"] > (wm.get("llm_max_id") or 0):
                changed.add(int(lo["session_id"]))
        signals = {"sessions": "ok", "llm": "ok", "asr": "ok", "crop": "ok"}
        return sorted(changed), signals


def _mk(tmp, cap=10000, **kw):
    """(db, cfg, sessions) — IncDB wrapper + Cfg with the new cap."""
    db, cfg, sessions = _setup(tmp, **kw)
    cfg.max_incremental_sessions = cap
    db = IncDB(db)
    return db, cfg, sessions


def _mk_exporter(db, cfg):
    return E.Exporter(db, cfg, log=lambda m: None)


def _mk_inc(db, cfg):
    return I.IncrementalExporter(_mk_exporter(db, cfg))


def _fp_map(recs):
    return {r["record_id"]: M.record_fingerprint(r) for r in recs}


def _qar_set(path):
    out = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    w = json.loads(line)
                    out.add((w["record"]["record_id"],
                             w["record"]["database_refs"]["session_id"]))
    return out


def _live_checksums(ex):
    return {n: E._sha256_of_file(os.path.join(ex.cfg.out_dir, n))
            for n in ex.live_output_files()}


# ----------------------------------------------------------------------
# mission-mandated: full rebuild vs incremental on the SAME snapshot
# ----------------------------------------------------------------------
def test_incremental_merge_equivalent_to_full_rebuild():
    with tempfile.TemporaryDirectory() as tmp:
        # ---- snapshot A: full build
        db, cfg, sessions = _mk(tmp)
        ex = _mk_exporter(db, cfg)
        m_full = ex.run(run_id="full-A", exported_at="2026-01-06 12:00:00")
        fp_full = _fp_map(ex.read_output())
        qar_full = _qar_set(os.path.join(cfg.out_dir, "quarantine.jsonl"))

        # ---- same snapshot, incremental merge on top of the same data:
        # state watermark = "past" (everything is inside the overlap
        # window, so the detector selects ALL sessions -> the slice IS
        # the whole corpus, merged into the identical live corpus)
        db2, cfg2, sessions2 = _mk(tmp)
        inc = _mk_inc(db2, cfg2)
        state = {"watermark": {"sessions_updated_at": "2020-01-01 00:00:00",
                               "sessions_max_id": 0,
                               "llm_finished_at": "2020-01-01 00:00:00",
                               "llm_max_id": 0},
                 "disk_signature": inc.disk_signature(),
                 "last_run_id": "full-A",
                 "last_records_written": m_full["records_written"]}
        I._atomic_write(os.path.join(cfg2.out_dir, "incremental_state.json"),
                        json.dumps(state))
        m_inc = inc.run()
        assert not m_inc.get("skipped")
        fp_inc = _fp_map(inc.ex.read_output())
        qar_inc = _qar_set(os.path.join(cfg2.out_dir, "quarantine.jsonl"))

        # equivalent logical datasets (record_id -> fingerprint)
        assert fp_full == fp_inc, (
            "full vs incremental differ: only-full=%r only-inc=%r "
            "diff-fp=%r" % (
                set(fp_full) - set(fp_inc),
                set(fp_inc) - set(fp_full),
                {k for k in set(fp_full) & set(fp_inc)
                 if fp_full[k] != fp_inc[k]}))
        assert qar_full == qar_inc
        assert m_inc["incremental"]["records_after"] == \
            m_full["records_written"]
        assert m_inc["mode"] == "incremental"
        # the full corpus was NOT replaced by the slice count
        assert m_inc["records_written"] == len(fp_full)


# ----------------------------------------------------------------------
def test_no_change_skip_is_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        db, cfg, sessions = _mk(tmp)
        inc = _mk_inc(db, cfg)
        m1 = inc.run()                     # first cycle -> full
        live1 = _live_checksums(inc.ex)
        state1 = json.load(open(os.path.join(cfg.out_dir,
                                             "incremental_state.json"),
                                encoding="utf-8"))

        m2 = inc.run()                     # second cycle -> skip
        assert m2.get("skipped") is True
        live2 = _live_checksums(inc.ex)
        assert live2 == live1, "a no-change cycle must not rewrite live"
        state2 = json.load(open(os.path.join(cfg.out_dir,
                                             "incremental_state.json"),
                                encoding="utf-8"))
        assert state2["watermark"] == state1["watermark"]
        assert state2["last_run_id"] == m1["run_id"]
        assert state2["last_action"] == "skip"
        # metrics must still be computable from the (untouched) disk
        from corpus import metrics
        values = metrics.compute(cfg)
        assert values["iranseda_corpus_records_total"] == \
            m1["records_written"]


def test_correction_updates_same_record():
    with tempfile.TemporaryDirectory() as tmp:
        db, cfg, sessions = _mk(tmp)
        inc = _mk_inc(db, cfg)
        m1 = inc.run()
        before = {r["record_id"]: r for r in inc.ex.read_output()}
        rid = "iranseda:ch14:e10000001"
        assert rid in before

        # a correction lands: a NEW llm_output row for session 1 with a
        # later finished_at + higher id (the llm signal fires)
        old_corr = next(lo for lo in db._inner.llm
                        if lo["job_type"] == "correct_subtitles")
        corr2 = dict(old_corr)
        corr2["id"] = 902
        corr2["finished_at"] = old_corr["finished_at"].replace(
            hour=11, minute=0)
        corr2["srt_content"] = old_corr["srt_content"] + " (revised)\n"
        db._inner.llm.append(corr2)

        m2 = inc.run()
        assert not m2.get("skipped")
        assert m2["mode"] == "incremental"
        after = {r["record_id"]: r for r in inc.ex.read_output()}
        # SAME record id, same total count, but a new fingerprint
        assert set(after) == set(before)
        assert m2["records_written"] == m1["records_written"]
        assert M.record_fingerprint(after[rid]) != \
            M.record_fingerprint(before[rid])
        # the unchanged sessions' records are byte-identical
        rid2 = "iranseda:ch14:e10000002"
        assert M.record_fingerprint(after[rid2]) == \
            M.record_fingerprint(before[rid2])


def test_no_live_corpus_falls_back_to_full():
    with tempfile.TemporaryDirectory() as tmp:
        db, cfg, sessions = _mk(tmp)
        inc = _mk_inc(db, cfg)
        os.makedirs(cfg.out_dir, exist_ok=True)
        # state claims a previous watermark but there is no live corpus
        state = {"watermark": {"sessions_updated_at": "2026-01-06 11:00:00",
                               "sessions_max_id": 99,
                               "llm_finished_at": "2026-01-06 10:05:00",
                               "llm_max_id": 901},
                 "disk_signature": inc.disk_signature()}
        I._atomic_write(os.path.join(cfg.out_dir, "incremental_state.json"),
                        json.dumps(state))
        m = inc.run()
        assert not m.get("skipped")
        assert m["mode"] == "full"
        assert len(inc.ex.read_output()) == m["records_written"]
        st = json.load(open(os.path.join(cfg.out_dir,
                                         "incremental_state.json"),
                            encoding="utf-8"))
        assert st["last_action"] == "full"


def test_bounded_cap_falls_back_to_full():
    with tempfile.TemporaryDirectory() as tmp:
        # cap=1: the detector (past watermark) finds >1 changed sessions
        db, cfg, sessions = _mk(tmp, cap=1)
        inc = _mk_inc(db, cfg)
        m1 = inc.run()
        state = {"watermark": {"sessions_updated_at": "2020-01-01 00:00:00",
                               "sessions_max_id": 0,
                               "llm_finished_at": "2020-01-01 00:00:00",
                               "llm_max_id": 0},
                 "disk_signature": inc.disk_signature(),
                 "last_run_id": m1["run_id"]}
        I._atomic_write(os.path.join(cfg.out_dir, "incremental_state.json"),
                        json.dumps(state))
        m2 = inc.run()
        assert not m2.get("skipped")
        assert m2["mode"] == "full"
        st = json.load(open(os.path.join(cfg.out_dir,
                                         "incremental_state.json"),
                            encoding="utf-8"))
        assert st["last_action"] == "full"


def test_failed_merge_keeps_live_and_state():
    with tempfile.TemporaryDirectory() as tmp:
        db, cfg, sessions = _mk(tmp)
        inc = _mk_inc(db, cfg)
        m1 = inc.run()
        live1 = _live_checksums(inc.ex)
        state_path = os.path.join(cfg.out_dir, "incremental_state.json")
        state1 = open(state_path, encoding="utf-8").read()

        # make the next cycle have real work (a new llm_output row) so
        # it takes the merge path and not the no-change skip
        old_corr = next(lo for lo in db._inner.llm
                        if lo["job_type"] == "correct_subtitles")
        corr2 = dict(old_corr)
        corr2["id"] = 902
        corr2["finished_at"] = old_corr["finished_at"].replace(hour=12, minute=5)
        db._inner.llm.append(corr2)

        # force a failure AFTER staging (validate raises in _commit)
        inc.ex._commit = (
            lambda *a, **k: (_ for _ in ()).throw(
                RuntimeError("injected commit failure")))
        try:
            inc.run()
            raise AssertionError("expected RuntimeError")
        except RuntimeError:
            pass

        live2 = _live_checksums(inc.ex)
        assert live2 == live1, "failed cycle must not touch live outputs"
        assert open(state_path, encoding="utf-8").read() == state1
        assert not any(n.startswith(".staging.") for n in
                       os.listdir(cfg.out_dir))


def test_export_lock_refuses_concurrent():
    with tempfile.TemporaryDirectory() as tmp:
        db, cfg, sessions = _mk(tmp)
        ex = _mk_exporter(db, cfg)
        os.makedirs(cfg.out_dir, exist_ok=True)
        lock_path = os.path.join(cfg.out_dir, E.LOCK_FILE)

        # hold the lock from a real FOREIGN child process (live pid)
        holder = subprocess.Popen(
            [sys.executable, "-c",
             "import os, sys, time\n"
             "p = sys.argv[1]\n"
             "open(p, 'w').write(str(os.getpid()) + ' held')\n"
             "time.sleep(10)\n"
             "try:\n    os.remove(p)\nexcept OSError:\n    pass\n",
             lock_path])
        try:
            # wait until the child has written its pid (alive)
            deadline = time.time() + 10
            while time.time() < deadline:
                if os.path.exists(lock_path):
                    with open(lock_path, encoding="utf-8") as f:
                        pid_s = (f.read().strip().split() or ["0"])[0]
                    if pid_s.isdigit() and int(pid_s) == holder.pid:
                        break
                time.sleep(0.05)
            else:
                raise AssertionError("holder child did not write lock")
            try:
                ex.run(run_id="locked")
                raise AssertionError("expected RuntimeError (lock held)")
            except RuntimeError as e:
                assert "export.lock" in str(e)
        finally:
            holder.kill()
            holder.wait()

        # a DEAD pid's lock is stale and taken over
        with open(lock_path, "w", encoding="utf-8") as f:
            f.write("999999 2026-01-01 00:00:00")
        m = ex.run(run_id="took-over")
        assert m["run_id"] == "took-over"
        assert not os.path.exists(lock_path), "lock must be released"


def test_incremental_manifest_has_change_detection_block():
    with tempfile.TemporaryDirectory() as tmp:
        db, cfg, sessions = _mk(tmp)
        inc = _mk_inc(db, cfg)
        m1 = inc.run()
        state = {"watermark": {"sessions_updated_at": "2020-01-01 00:00:00",
                               "sessions_max_id": 0,
                               "llm_finished_at": "2020-01-01 00:00:00",
                               "llm_max_id": 0},
                 "disk_signature": inc.disk_signature(),
                 "last_run_id": m1["run_id"]}
        I._atomic_write(os.path.join(cfg.out_dir, "incremental_state.json"),
                        json.dumps(state))
        m2 = inc.run()
        cd = m2["change_detection"]
        assert cd["changed_session_count"] >= len(sessions)
        assert set(cd["signals"].keys()) == {"sessions", "llm", "asr", "crop"}
        assert m2["incremental"]["records_before"] == m1["records_written"]
        # state advanced with the new watermark + disk signature
        st = json.load(open(os.path.join(cfg.out_dir,
                                         "incremental_state.json"),
                            encoding="utf-8"))
        assert st["last_action"] == "incremental"
        assert st["disk_signature"] is not None
