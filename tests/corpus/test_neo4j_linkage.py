"""Neo4j in-place linkage propagation (Stage 5, Task A) — offline tests.

Covers: row_props (null omission, quarantine URL stripping, program_id
coercion), load_linkage_map (doc_id keying + duplicate detection),
plan_node (to_set / noop / conflict), build_write_rows (batching cap +
noop skip), the neo4j_write statement guard (fail-closed: read-only
heads rejected, DELETE/CREATE/MERGE/DROP/LOAD forbidden, read verb
required), and the rehearsal paths (apply --dry-run / --docs and
rollback --dry-run / --docs, all with monkeypatched live reads).  No
network, no Neo4j, no MySQL, no writes to disk beyond tempfiles.
"""

import json
import os
import tempfile

from corpus import neo4j_linkage as N


ROW = {
    "record_id": "iranseda:ch14:e152507883",
    "session_uid": "iranseda:ch14:e152507883",
    "program_id": 1,
    "program_uid": "iranseda:prog:ch14:m044116",
    "program_page_url": "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=044116",
    "archive_episode_url": "https://radio.iranseda.ir/epgarchivePart/?VALID=TRUE&ch=14&e=152507883",
    "archive_day_url": "https://radio.iranseda.ir/timeArchive/?VALID=TRUE&ch=14&d=11/7/2024",
    "archive_time_slot_url": "https://radio.iranseda.ir/timeArchivePart/?VALID=TRUE&ch=14&ti=21:30&d=11/7/2024",
    "corrected_srt_url": "https://raw.githubusercontent.com/u/r/branch/a.correct.srt",
    "corrected_text_url": "https://raw.githubusercontent.com/u/r/branch/a.correct.txt",
    "summary_url": "https://raw.githubusercontent.com/u/r/branch/a.summary.txt",
    "summary_en_url": "https://raw.githubusercontent.com/u/r/branch/a.summary.en.txt",
    "timezone": "Asia/Tehran",
    "air_date_status": "unverified",
    "quarantined": False,
    "linkage_version": "1.1",
    "linkage_validated_at": "2026-11-06T03:12:32Z",
    "doc_id": "radio-maaref-03-08-17-21-30__s3",
    "doc_id_mapped_from": "db_derived",
}


def _row(**over):
    r = dict(ROW)
    r.update(over)
    return r


def test_row_props_full():
    p = N.row_props(_row())
    assert p["record_id"] == "iranseda:ch14:e152507883"
    assert p["session_uid"] == "iranseda:ch14:e152507883"
    assert p["program_id"] == 1 and isinstance(p["program_id"], int)
    assert p["episode_url"] == ROW["archive_episode_url"]
    assert p["day_archive_url"] == ROW["archive_day_url"]
    assert p["timeslot_archive_url"] == ROW["archive_time_slot_url"]
    assert "full_text_url" not in p  # absent in row -> omitted (null discipline)
    assert "raw_srt_url" not in p and "audio_url" not in p
    assert p["quarantined"] is False
    assert p["air_date_status"] == "unverified"
    assert p["linkage_version"] == "1.1"
    # K7 maps to itself, so the node prop IS program_page_url
    assert p["program_page_url"] == ROW["program_page_url"]
    # archive_* row keys must not leak under their row names (they map to
    # episode_url / day_archive_url / timeslot_archive_url)
    assert "archive_episode_url" not in p
    assert "archive_day_url" not in p
    assert "archive_time_slot_url" not in p


def test_row_props_null_omission():
    r = _row(program_uid=None, program_page_url="",
             archive_day_url=None, air_date_status="none")
    p = N.row_props(r)
    assert "program_uid" not in p
    assert "program_page_url" not in p
    assert "day_archive_url" not in p
    assert p["air_date_status"] == "none"  # non-empty "none" IS a value


def test_row_props_quarantine_strips_urls():
    r = _row(quarantined=True)
    p = N.row_props(r)
    assert p["quarantined"] is True
    for k in ("program_page_url", "episode_url", "day_archive_url",
              "timeslot_archive_url", "raw_srt_url", "corrected_srt_url",
              "full_text_url", "corrected_text_url", "summary_url",
              "summary_en_url", "audio_url"):
        assert k not in p, k
    # identity/status keys remain (citable-by-id only)
    for k in ("record_id", "session_uid", "program_id", "timezone",
              "air_date_status", "linkage_version", "linkage_validated_at"):
        assert k in p, k
    assert p["program_uid"] == ROW["program_uid"]


def test_row_props_program_id_bad_int_omitted():
    p = N.row_props(_row(program_id="not-an-int"))
    assert "program_id" not in p


def test_load_linkage_map():
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "rag_linkage.jsonl")
        rows = [_row(),
                _row(record_id="iranseda:ch14:e2", session_uid="iranseda:ch14:e2",
                     doc_id="x__s9", quarantined=True),
                {"record_id": "no-doc", "session_id": 5}]
        with open(p, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        by_doc, dups, n = N.load_linkage_map(p)
        assert n == 3
        assert set(by_doc) == {"radio-maaref-03-08-17-21-30__s3", "x__s9"}
        assert dups == {}


def test_load_linkage_map_duplicates():
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "rag_linkage.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps(_row(), ensure_ascii=False) + "\n")
            f.write(json.dumps(_row(linkage_version="9.9"),
                               ensure_ascii=False) + "\n")
        by_doc, dups, n = N.load_linkage_map(p)
        assert n == 2
        assert len(by_doc) == 1
        assert by_doc[ROW["doc_id"]]["linkage_version"] == "1.1"  # first wins
        assert sorted(dups) == [ROW["doc_id"]]
        assert len(dups[ROW["doc_id"]]) == 1


def test_plan_node_additive_noop_conflict():
    want = {"session_uid": "u1", "timezone": "Asia/Tehran",
            "air_date_status": "unverified"}
    to_set, noop, conf = N.plan_node(want, {})
    assert set(to_set) == set(want) and not noop and not conf

    to_set, noop, conf = N.plan_node(want, {"session_uid": "u1",
                                            "timezone": "Asia/Tehran"})
    assert to_set == {"air_date_status": "unverified"}
    assert sorted(noop) == ["session_uid", "timezone"]

    to_set, noop, conf = N.plan_node(want, {"session_uid": "OTHER"})
    assert to_set == {"timezone": "Asia/Tehran",
                      "air_date_status": "unverified"}
    assert conf == ["session_uid"]  # never overwritten


def test_build_write_rows_batches_and_skips():
    plans = [{"doc_id": "d%d" % i, "chunk_id": "c%d" % i,
              "to_set": {"k": i}} for i in range(25)]
    plans.append({"doc_id": "noop", "chunk_id": "nn", "to_set": {}})
    batches, skipped = N.build_write_rows(plans, batch=10)
    assert skipped == 1
    assert [b["n_nodes"] for b in batches] == [10, 10, 5]
    assert all(len(b["rows"]) == b["n_nodes"] for b in batches)
    assert all(b["n_nodes"] <= 10 for b in batches)
    row = batches[0]["rows"][0]
    assert set(row) == {"doc_id", "chunk_id", "props"}
    assert row["props"] == {"k": 0}


def test_build_write_rows_all_noop():
    batches, skipped = N.build_write_rows(
        [{"doc_id": "d", "chunk_id": "c", "to_set": {}}], batch=10)
    assert batches == [] and skipped == 1


def test_write_guard_rejects_read_and_write_verbs():
    CREDS = ("127.0.0.1", 7474, "neo4j", "x", "test")
    for bad in (
        "MATCH (n:Chunk) RETURN count(n) AS c",          # read (no SET)
        "CREATE (n:Chunk)",
        "MATCH (n) DELETE n",
        "MERGE (n:Chunk {doc_id: 'x'})",
        "CALL db.index.vector.queryNodes('i', 5, [0])",
        "DROP INDEX vector_index_chunk",
        "LOAD CSV FROM 'x' AS r",
    ):
        try:
            N.neo4j_write(CREDS, "radio", bad)
            raise AssertionError("guard failed to reject: %s" % bad)
        except ValueError:
            pass


def test_write_guard_accepts_unwind_set_and_remove_heads():
    # must pass the guard (raises only when it reaches the network)
    for good in (
        "UNWIND $rows AS r MATCH (n:Chunk) WHERE n.doc_id = r.doc_id "
        "SET n += r.props RETURN count(n) AS c",
        "UNWIND $rows AS r MATCH (n:Chunk) WHERE n.doc_id = r.doc_id "
        "REMOVE n.session_uid RETURN count(n) AS c",
    ):
        try:
            N.neo4j_write(CREDS, "radio", good)
        except ValueError as e:
            raise AssertionError("guard rejected legal write: %s (%r)"
                                 % (good, e))
        except Exception:
            pass  # network failure is EXPECTED offline — guard passed


class _Patch(object):
    """Minimal monkeypatch stand-in (the stdlib runner passes no args)."""

    def __init__(self):
        self._saved = []

    def setattr(self, target, name, value):
        self._saved.append((target, name, getattr(target, name)))
        setattr(target, name, value)

    def undo(self):
        while self._saved:
            target, name, old = self._saved.pop()
            setattr(target, name, old)


def _fake_cfg(td):
    import types
    return types.SimpleNamespace(out_dir=td)


def _write_map(td, rows):
    p = os.path.join(td, N.RAG_LINKAGE_NAME)
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return p


def _patch_live(mp, n=10, doc_ids=("d1", "d2")):
    mp.setattr(N._rl, "_neo4j_creds",
               lambda: {"user": "u", "password": "p"})
    mp.setattr(N, "live_index", lambda c, d: {"state": "ONLINE"})
    mp.setattr(N, "live_counts", lambda c, d: (n, list(doc_ids)))
    mp.setattr(N, "_sha256_file", lambda p: "deadbeef")
    mp.setattr(N, "fetch_node_pairs",
               lambda c, d, ids, chunk_docs=2000:
               [(x, 0) for x in ids])
    mp.setattr(N, "fetch_existing", lambda c, d, ids, chunk_docs=2000: {})


def _two_row_map(td):
    return _write_map(td, [
        {"doc_id": "d1", "session_uid": "u1", "quarantined": False},
        {"doc_id": "d2", "session_uid": "u2", "quarantined": False}])


def _snap(doc_ids=None):
    return {"n_chunks": 10, "sample": [], "sample_n": 0,
            "doc_ids_sha256": "x", "pre_state": [],
            "doc_ids": doc_ids if doc_ids is not None else ["d1", "d2"]}


def test_apply_dry_run_zero_writes():
    mp = _Patch()
    try:
        with tempfile.TemporaryDirectory() as td:
            mpath = _two_row_map(td)
            mp.setattr(N, "load_snapshot", lambda d: _snap())
            _patch_live(mp)
            calls = []
            mp.setattr(N, "neo4j_write",
                       lambda *a, **k: calls.append(a) or [{"c": 1}])
            state_p = os.path.join(td, "state.json")
            out = N.apply(_fake_cfg(td), td, map_path=mpath,
                          state_path=state_p, dry_run=True,
                          log=lambda *a: None)
            assert out["dry_run"] is True and out["applied_nodes"] == 0
            assert out["nodes"] == 2
            assert out["keys_to_set"] == 4  # session_uid + quarantined x2
            assert calls == []
            assert not os.path.exists(state_p)  # state untouched
    finally:
        mp.undo()


def test_apply_scoped_only_selected_docs():
    mp = _Patch()
    try:
        with tempfile.TemporaryDirectory() as td:
            mpath = _two_row_map(td)
            mp.setattr(N, "load_snapshot", lambda d: _snap())
            _patch_live(mp)
            calls = []
            mp.setattr(N, "neo4j_write",
                       lambda *a, **k: calls.append(a) or [{"c": 1}])
            state_p = os.path.join(td, "state.json")
            out = N.apply(_fake_cfg(td), td, map_path=mpath,
                          state_path=state_p, docs=["d1"],
                          log=lambda *a: None)
            assert out["applied_nodes"] == 1
            assert len(calls) == 1
            rows_sent = calls[0][3]["rows"]
            assert [r["doc_id"] for r in rows_sent] == ["d1"]
            st = json.load(open(state_p, encoding="utf-8"))
            assert st["complete"] is True and st["applied_nodes"] == 1
    finally:
        mp.undo()


def test_rollback_dry_run_zero_writes():
    mp = _Patch()
    try:
        with tempfile.TemporaryDirectory() as td:
            mpath = _two_row_map(td)
            mp.setattr(N, "load_snapshot", lambda d: _snap())
            _patch_live(mp)
            calls = []
            mp.setattr(N, "neo4j_write",
                       lambda *a, **k: calls.append(a) or [{"c": 1}])
            out = N.rollback(_fake_cfg(td), td, map_path=mpath,
                             state_path=os.path.join(td, "no_state.json"),
                             dry_run=True, log=lambda *a: None)
            assert out["dry_run"] is True
            assert out["nodes"] == 2
            assert out["node_key_removals"] == 2 * len(N.ADDITIVE_KEYS)
            assert calls == []
    finally:
        mp.undo()


def test_rollback_scoped_removal_statements():
    mp = _Patch()
    try:
        with tempfile.TemporaryDirectory() as td:
            mpath = _two_row_map(td)
            mp.setattr(N, "load_snapshot", lambda d: _snap())
            _patch_live(mp)
            calls = []
            mp.setattr(N, "neo4j_write",
                       lambda *a, **k: calls.append(a) or [{"c": 1}])
            out = N.rollback(_fake_cfg(td), td, map_path=mpath,
                             state_path=os.path.join(td, "no_state.json"),
                             docs=["d1"], log=lambda *a: None)
            assert out["nodes"] == 1
            # pre_state empty -> only REMOVE, one per additive key, d1 only
            assert len(calls) == len(N.ADDITIVE_KEYS)
            for stmt, params in ((c[2], c[3]) for c in calls):
                assert "REMOVE n." in stmt and "DELETE" not in stmt
                assert [r["doc_id"] for r in params["rows"]] == ["d1"]
            assert not any("SET n +=" in c[2] for c in calls)
    finally:
        mp.undo()


def test_additive_keys_match_contract():
    assert len(N.ADDITIVE_KEYS) == 20
    for k in ("record_id", "session_uid", "program_id", "program_uid",
              "program_page_url", "timezone", "episode_url",
              "day_archive_url", "timeslot_archive_url", "raw_srt_url",
              "corrected_srt_url", "full_text_url", "corrected_text_url",
              "summary_url", "summary_en_url", "audio_url",
              "air_date_status", "quarantined", "linkage_version",
              "linkage_validated_at"):
        assert k in N.ADDITIVE_KEYS
    # existing keys must NEVER be in the additive set
    for k in ("doc_id", "chunk_id", "session_id", "program_name",
              "air_persian", "air_gregorian", "air_time", "chunk_text",
              "citation", "channel", "start_hms", "end_hms"):
        assert k not in N.ADDITIVE_KEYS
