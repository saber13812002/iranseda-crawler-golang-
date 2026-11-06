"""RAG linkage dataset (Stage 4, Task A.5) — offline pure-function tests.

Covers: derive_doc_id, neo4j_query read-only guard, quarantine_ids,
_load_validation_cache (both file shapes + absence), _rec_archive_urls
(status discipline + cache "invalid" exclusion), build_rag_row (K1-K22
null discipline, quarantine URL stripping, cache exclusion),
_clean_asset_entry / build_asset_rows, and the end-to-end build_rag_row
asset-URL injection path (K14-K19 published-only).

No network, no MySQL, no Neo4j, no git.
"""

import json
import os
import tempfile
import urllib.error
import urllib.request

from corpus import rag_linkage as R
from corpus import assets as A

from corpus.linkage import (
    LINK_EPISODE, LINK_DAY_ARCHIVE, LINK_TIME_SLOT, LINK_PROGRAM)

CREDS = ("127.0.0.1", 7474, "neo4j", "sekret", "env")

SESSION = {
    "id": 4242, "program_id": 11,
    "link": "https://radio.iranseda.ir/Radio/?ch=14&e=44116",
    "filename": "radio-maaref-05-07-19-13-30.mp3",
}

CORPUS_REC = {
    "record_id": "iranseda:ch14:e44116",
    "session_uid": "iranseda:ch14:e44116",
    "session_uid_status": "link",
    "program_uid": "iranseda:prog:ch14:m044116",
    "program_uid_status": "ok",
    "database_refs": {"session_id": 4242, "program_id": 11},
    "program": {"name": "برنامه تست", "url": "u"},
    "broadcast": {
        "jalali": {"date": "1403-05-07", "time": "19:13:00"},
        "gregorian": {"date": "2024-08-01", "time": "19:13:00"},
    },
    "linkage": {
        "air_date_status": "confirmed",
        "links": [
            {"type": LINK_EPISODE, "url": "https://ep",
             "url_normalized": "https://ep", "status": "eligible",
             "reason": None},
            {"type": LINK_DAY_ARCHIVE, "url": "https://day",
             "url_normalized": "https://day", "status": "eligible",
             "reason": None},
            {"type": LINK_TIME_SLOT, "url": "https://slot",
             "url_normalized": "https://slot", "status": "eligible",
             "reason": None},
            {"type": LINK_PROGRAM, "url": "https://prog",
             "url_normalized": "https://prog", "status": "eligible",
             "reason": None},
        ],
    },
}

CACHE = {
    "https://ep": {"status": "valid", "reason": None,
                   "title": "ت", "at": "2026-01-01T00:00:00Z"},
    "https://day": {"status": "invalid", "reason": "404",
                    "title": None, "at": "2026-01-01T00:00:00Z"},
}


# ---------------------------------------------------------------------------
# derive_doc_id — the exact radio-rag/extract.py rule

def test_derive_doc_id_rule():
    assert R.derive_doc_id(SESSION) == "radio-maaref-05-07-19-13-30__s4242"


def test_derive_doc_id_strips_at_first_dot():
    # extract.py rule: filename minus everything from its FIRST dot —
    # a.b.mp3 -> stem "a" (NOT the last-extension stem "a.b")
    s = {"id": 7, "filename": "a.b.mp3"}
    assert R.derive_doc_id(s) == "a__s7"


def test_derive_doc_id_absent_when_no_filename():
    assert R.derive_doc_id({"id": 7, "filename": None}) is None
    assert R.derive_doc_id({"id": 7, "filename": "  "}) is None


# ---------------------------------------------------------------------------
# neo4j_query read-only guard

def test_neo4j_query_rejects_write_verbs():
    for bad in ("CREATE (n:Chunk)", "MATCH (n) DELETE n",
                "SET n.x = 1", "MERGE (n:Chunk)", "DROP DATABASE radio",
                ""):
        try:
            R.neo4j_query(CREDS, statement=bad)
            raise AssertionError("should have raised for %r" % bad)
        except ValueError:
            pass


def test_neo4j_query_allows_read_heads():
    # must pass the guard (then fail on the network call — no Neo4j here)
    for ok in ("MATCH (n:Chunk) RETURN n",
               "RETURN 1",
               "SHOW DATABASES",
               "EXPLAIN MATCH (n) RETURN n"):
        try:
            R.neo4j_query(CREDS, statement=ok)
        except ValueError as exc:
            raise AssertionError("read head rejected: %s" % exc)
        except (urllib.error.URLError, OSError, TimeoutError):
            pass  # expected: no server


# ---------------------------------------------------------------------------
def test_neo4j_query_parses_columns_payload():
    # regression (Stage 4 live run): neo4j 5.x tx/commit payloads carry
    # "columns", not "fields" - a "fields"-only parser silently dropped
    # every doc_id mapping (live run: 4,148 rows -> 0 pairs).
    import io

    class _FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()

    payload = {"results": [
        {"columns": ["doc_id", "session_id"],
         "data": [{"row": ["radio-maaref-x__s3", 3],
                   "meta": [None, None]}]}],
        "errors": []}
    body = json.dumps(payload).encode("utf-8")
    real_urlopen = urllib.request.urlopen
    urllib.request.urlopen = lambda req, timeout=None: _FakeResp(body)
    try:
        rows = R.neo4j_query(
            CREDS, statement="MATCH (n:Chunk) RETURN 1")
    finally:
        urllib.request.urlopen = real_urlopen
    assert rows == [{"doc_id": "radio-maaref-x__s3",
                     "session_id": 3}]


def test_neo4j_query_parses_legacy_fields_payload():
    # the older payload shape (results[0].fields) must keep working
    import io

    class _FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()

    payload = {"results": [
        {"fields": ["doc_id", "session_id"],
         "data": [{"row": ["doc-1", 9], "meta": [None, None]}]}],
        "errors": []}
    body = json.dumps(payload).encode("utf-8")
    real_urlopen = urllib.request.urlopen
    urllib.request.urlopen = lambda req, timeout=None: _FakeResp(body)
    try:
        rows = R.neo4j_query(
            CREDS, statement="MATCH (n:Chunk) RETURN 1")
    finally:
        urllib.request.urlopen = real_urlopen
    assert rows == [{"doc_id": "doc-1", "session_id": 9}]
# quarantine_ids / _load_validation_cache

def test_quarantine_ids_both_shapes(tmp=None):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "quarantine.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps(
                {"record": {"record_id": "iranseda:ch14:e1"},
                 "quarantine": {"policy": "P", "class": "B"}},
                ensure_ascii=False) + "\n")
            f.write(json.dumps(
                {"quarantine": {"record_id": "iranseda:ch14:e2"}},
                ensure_ascii=False) + "\n")
            f.write("\n")
            f.write("not-json\n")
        assert R.quarantine_ids(d) == {"iranseda:ch14:e1",
                                       "iranseda:ch14:e2"}


def test_quarantine_ids_missing_file():
    with tempfile.TemporaryDirectory() as d:
        assert R.quarantine_ids(d) == set()


def test_validation_cache_jsonl_of_objects():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, R.VALIDATION_CACHE_NAME)
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps({"https://a": {"status": "valid"}})
                    + "\n")
            f.write(json.dumps({"https://b": {"status": "invalid",
                                               "reason": "404"}})
                    + "\n")
        cache = R._load_validation_cache(d)
        assert cache["https://a"]["status"] == "valid"
        assert cache["https://b"]["status"] == "invalid"


def test_validation_cache_single_object():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, R.VALIDATION_CACHE_NAME)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"https://c": {"status": "valid",
                                     "title": "ت"}}, f)
        cache = R._load_validation_cache(d)
        assert cache == {"https://c": {"status": "valid", "title": "ت"}}


def test_validation_cache_missing_is_empty():
    with tempfile.TemporaryDirectory() as d:
        assert R._load_validation_cache(d) == {}


# ---------------------------------------------------------------------------
# _rec_archive_urls — status discipline (§7.2.4)

def test_archive_urls_eligible_served():
    urls = R._rec_archive_urls(CORPUS_REC, {})
    assert urls == {
        "archive_episode_url": "https://ep",
        "archive_day_url": "https://day",
        "archive_time_slot_url": "https://slot",
        "program_page_url": "https://prog",
    }


def test_archive_urls_cache_invalid_excluded():
    urls = R._rec_archive_urls(CORPUS_REC, CACHE)
    assert "archive_day_url" not in urls  # cache says 404
    assert urls["archive_episode_url"] == "https://ep"  # valid stays


def test_archive_urls_not_eligible_and_excluded_never_served():
    rec = {
        "linkage": {
            "links": [
                {"type": LINK_EPISODE, "url": "https://x",
                 "status": "not_eligible", "reason": "no_date"},
                {"type": LINK_PROGRAM, "url": "https://y",
                 "status": "excluded", "reason": "quarantined"},
                {"type": LINK_DAY_ARCHIVE, "url": None,
                 "status": "eligible", "reason": None},
            ],
        },
    }
    assert R._rec_archive_urls(rec, {}) == {}
    assert R._rec_archive_urls({"no": "linkage"}, CACHE) == {}


# ---------------------------------------------------------------------------
# build_rag_row — K1-K22 null discipline

def test_build_rag_row_full():
    row = R.build_rag_row(
        SESSION, CORPUS_REC, False,
        "radio-maaref-05-07-19-13-30__s4242", "neo4j",
        cache=CACHE, validated_at="2026-01-02T00:00:00Z")
    assert row["record_id"] == "iranseda:ch14:e44116"          # K1
    assert row["session_id"] == 4242                           # K2
    assert row["session_uid"] == "iranseda:ch14:e44116"        # K3
    assert row["program_id"] == 11                             # K4
    assert row["program_title"] == "برنامه تست"                # K5
    assert row["program_uid"] == "iranseda:prog:ch14:m044116"  # K6
    assert row["program_page_url"] == "https://prog"           # K7
    assert row["broadcast_date_persian"] == "1403-05-07"       # K8
    assert row["broadcast_date_gregorian"] == "2024-08-01"     # K8
    assert row["broadcast_time"] == "19:13:00"                 # K9
    assert row["timezone"] == "Asia/Tehran"                    # K10
    assert row["archive_episode_url"] == "https://ep"          # K11
    assert row["archive_time_slot_url"] == "https://slot"      # K13
    assert "archive_day_url" not in row                        # invalid in cache
    assert row["air_date_status"] == "confirmed"               # K20
    assert row["quarantined"] is False                          # K21
    assert row["linkage_version"] == "1.1"                     # K22
    assert row["linkage_validated_at"] == "2026-01-02T00:00:00Z"
    assert row["doc_id"] == "radio-maaref-05-07-19-13-30__s4242"
    assert row["doc_id_mapped_from"] == "neo4j"
    assert "doc_id_missing" not in row


def test_build_rag_row_quarantine_strips_all_urls():
    rec = dict(CORPUS_REC)
    rec["_rag_asset_urls"] = {"raw_srt_url": "https://raw",
                              "audio_url": "https://mp3"}
    row = R.build_rag_row(SESSION, rec, True, "doc__s4242",
                          "neo4j", cache=CACHE)
    assert row["quarantined"] is True
    for k in ("program_page_url", "archive_episode_url",
              "archive_day_url", "archive_time_slot_url",
              "raw_srt_url", "audio_url"):
        assert k not in row, k


def test_build_rag_row_asset_urls_injected_published_only():
    rec = dict(CORPUS_REC)
    rec["_rag_asset_urls"] = {
        "raw_srt_url": "https://raw",
        "summary_url": None,       # not published -> None -> omitted
        "full_text_url": "https://txt",
    }
    row = R.build_rag_row(SESSION, rec, False, None, "missing")
    assert row["raw_srt_url"] == "https://raw"                 # K14
    assert row["full_text_url"] == "https://txt"               # K16
    assert "summary_url" not in row
    assert row["doc_id_missing"] is True
    assert "doc_id" not in row
    assert "doc_id_mapped_from" not in row


def test_build_rag_row_null_discipline_no_record():
    s = {"id": 5, "program_id": 11, "link": None, "filename": None}
    row = R.build_rag_row(s, None, False, None, "missing")
    assert row["session_id"] == 5
    # fallback identity from the session row itself (assets.session_uid)
    assert row["record_id"] == "iranseda:db11:s5"
    assert row["session_uid"] == "iranseda:db11:s5"
    assert row["timezone"] == "Asia/Tehran"
    assert row["quarantined"] is False
    assert row["air_date_status"] == "none"
    assert row["linkage_version"] == "1.1"
    # K4 present (session has program_id 11); the rest absent (R5)
    assert row["program_id"] == 11
    for k in ("program_title", "program_uid",
              "broadcast_date_persian", "broadcast_date_gregorian",
              "broadcast_time", "program_page_url", "archive_episode_url",
              "archive_day_url", "archive_time_slot_url",
              "raw_srt_url", "doc_id"):
        assert k not in row, k


def test_build_rag_row_air_status_defaults_none_without_linkage():
    rec = {"record_id": "r"}
    row = R.build_rag_row(SESSION, rec, False, None, "missing")
    assert row["air_date_status"] == "none"
    assert "program_title" not in row  # no program block
    # no session_uid in the record -> falls back to record_id
    assert row["session_uid"] == "r"


# ---------------------------------------------------------------------------
# asset manifest rows

def _entry(**over):
    e = {
        "asset_type": "audio", "filename": "x.mp3",
        "relpath": "downloads/x.mp3", "branch": "download-db",
        "raw_url": "https://raw", "blob_url": "https://blob",
        "sha256": "abc", "size_bytes": 1234,
        "exists_on_disk": True, "exists_in_git_tree": True,
        "published": A.PUBLISHED, "publishing_commit_sha": None,
        "produced_at": "2026-01-01T00:00:00Z",
        "processing_version": "m1", "source": "db:filename",
        "quarantined": False, "operational_branch_present": None,
        "http_status": None, "http_reason": None, "sha_match": None,
        "http_verified_at": None,
        "_raw_url": "https://raw-int", "_blob_url": "https://blob-int",
        "fingerprint": None,
    }
    e.update(over)
    return e


def _registry():
    return [
        {"session_id": 1, "program_id": 11,
         "session_uid": "iranseda:ch14:e1", "quarantined": False,
         "assets": [_entry()]},
        {"session_id": 2, "program_id": 11,
         "session_uid": "iranseda:ch14:e2", "quarantined": True,
         "assets": [_entry(asset_type="corrected_srt",
                           published=A.EXCLUDED, raw_url=None,
                           blob_url=None, quarantined=True,
                           exists_on_disk=True,
                           exists_in_git_tree=True)]},
    ]


def test_clean_asset_entry_strips_internal_keeps_c8():
    c = R._clean_asset_entry(_entry())
    assert "_raw_url" not in c and "_blob_url" not in c
    assert "fingerprint" not in c
    assert c["size_bytes"] == 1234       # C8 is a contract field
    assert c["sha256"] == "abc"
    assert c["raw_url"] == "https://raw"
    assert c["produced_at"] == "2026-01-01 00:00:00"  # normalized


def test_clean_asset_entry_normalizes_datetime_obj():
    import datetime
    e = _entry()
    e["produced_at"] = datetime.datetime(2026, 1, 2, 3, 4, 5)
    assert R._clean_asset_entry(e)["produced_at"] == "2026-01-02 03:04:05"


def test_build_asset_rows_one_row_per_asset():
    rows = R.build_asset_rows(_registry())
    assert len(rows) == 2
    r0, r1 = rows
    assert r0["session_id"] == 1 and r0["quarantined"] is False
    assert r0["asset_type"] == "audio"
    assert r0["relpath"] == "downloads/x.mp3"
    assert r1["session_id"] == 2 and r1["quarantined"] is True
    assert r1["asset_type"] == "corrected_srt"
    assert r1["published"] == A.EXCLUDED
    assert r1["raw_url"] is None


def test_build_asset_rows_empty_registry():
    assert R.build_asset_rows([]) == []


# ---------------------------------------------------------------------------
# main() wiring (fake DB / fake scan / fake assets — no network, no git)

def test_main_end_to_end_fake_deps():
    with tempfile.TemporaryDirectory() as root:
        out = os.path.join(root, "data", "corpus")
        os.makedirs(os.path.join(root, "downloads"))
        os.makedirs(out)
        # a small published asset on disk (root-relative relpath)
        mp3 = os.path.join(root, "downloads", "radio-maaref-05-07-19-13-30.mp3")
        with open(mp3, "wb") as f:
            f.write(b"ID3fake" * 10)

        # --- fake DB (monkeypatched into corpus.database) -------------------
        from corpus import database as DB

        class _FakeDB:
            def __init__(self, cfg):
                pass

            def connect(self):
                pass

            def close(self):
                pass

            def fetch_sessions(self, batch_size=1000, where=None,
                               params=None):
                return (1, iter([SESSION]))

            def fetch_llm_outputs(self, session_ids=None, where=None,
                                  params=None):
                return (0, iter([]))

            def table_counts(self):
                return {"radio_program_sessions": 1}

        real_db = DB.Database
        DB.Database = _FakeDB

        # --- fake scan (load_github / git_out) ------------------------------
        from corpus import scan_assets as SCAN

        real_lg, real_go = SCAN.load_github, SCAN.git_out

        SCAN.load_github = lambda root, repo: {
            "user": "u", "repo": "r", "branch": "download-db"}
        SCAN.git_out = lambda repo, args, timeout=180: (
            0, "downloads/radio-maaref-05-07-19-13-30.mp3\n", "")

        # --- fake assets (build_registry / check_disk) -----------------------
        real_br, real_cd = A.build_registry, A.check_disk

        A.build_registry = lambda sessions, llm, gh, operational_branch=None, \
            quarantine_ids=None: [
                {"session_id": 4242, "program_id": 11,
                 "session_uid": "iranseda:ch14:e44116",
                 "quarantined": False, "asset_count": 1,
                 "assets": [_entry(relpath=(
                     "downloads/radio-maaref-05-07-19-13-30.mp3"))]},
            ]
        def _fake_check_disk(registry, downloads_dir,
                             sha_cap_bytes=None, fp_chunk=None):
            # mirrors the real contract: C9 (+C8) from the local tree,
            # then recompute C11 (C5 stays hidden until PUBLISHED)
            for s in registry:
                for a in s["assets"]:
                    p = os.path.join(root, *a["relpath"].split("/"))
                    if os.path.isfile(p):
                        a["exists_on_disk"] = True
                        a["size_bytes"] = os.path.getsize(p)
                        a["sha256"] = None  # cap=0 (no_sha)
                    else:
                        a["exists_on_disk"] = False
                        a["size_bytes"] = None
                        a["sha256"] = None
                    A._recompute_published(a)
            return 1

        A.check_disk = _fake_check_disk

        # --- live corpus record + validation cache ---------------------------
        with open(os.path.join(out, "corpus.jsonl"), "w",
                  encoding="utf-8") as f:
            f.write(json.dumps(CORPUS_REC, ensure_ascii=False) + "\n")
        with open(os.path.join(out, R.VALIDATION_CACHE_NAME), "w",
                  encoding="utf-8") as f:
            json.dump(CACHE, f)

        class Cfg(object):
            pass
        Cfg.root = root
        Cfg.downloads_dir = os.path.join(root, "downloads")
        Cfg.out_dir = out

        logs = []
        try:
            summary = R.main(Cfg(), log=logs.append, neo4j=False,
                             no_sha=True)
        finally:
            DB.Database = real_db
            SCAN.load_github, SCAN.git_out = real_lg, real_go
            A.build_registry, A.check_disk = real_br, real_cd

        # summary shape (what the CLI prints)
        assert summary["rag_rows"] == 1
        assert summary["corpus_records_read"] == 1
        assert summary["doc_id"]["source"] == "unavailable"
        assert summary["doc_id"]["from_db_derived"] == 1
        assert summary["sha_cap"] == 0  # --no-sha -> presence-only
        assert summary["git_tree_paths"] == 1

        # rag_linkage.jsonl content
        rag = os.path.join(out, R.RAG_LINKAGE_NAME)
        with open(rag, encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
        assert len(rows) == 1
        row = rows[0]
        assert row["record_id"] == "iranseda:ch14:e44116"
        assert row["doc_id"] == "radio-maaref-05-07-19-13-30__s4242"
        assert row["doc_id_mapped_from"] == "db_derived"
        # K14 asset URL from the (published) registry entry — C5 is
        # recomputed from the internal _raw_url on _recompute_published
        assert row["audio_url"] == "https://raw-int"
        assert "archive_day_url" not in row  # cache invalid

        # asset_manifest.jsonl content
        man = os.path.join(out, R.ASSET_MANIFEST_NAME)
        with open(man, encoding="utf-8") as f:
            mrows = [json.loads(l) for l in f if l.strip()]
        assert len(mrows) == 1
        assert mrows[0]["session_id"] == 4242
        assert mrows[0]["relpath"] == (
            "downloads/radio-maaref-05-07-19-13-30.mp3")
        assert mrows[0]["size_bytes"] == 70      # b"ID3fake" * 10
        assert mrows[0]["published"] == A.PUBLISHED
        assert mrows[0]["raw_url"] == "https://raw-int"

        # map_id = sha256 of the rag file content
        import hashlib
        with open(rag, "rb") as f:
            expect = hashlib.sha256(f.read()).hexdigest()
        assert summary["map_id"] == expect
