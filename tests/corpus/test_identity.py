"""Stage 1 — Class B identity investigation: regression tests (no DB)."""

import datetime
import json
import os
import tempfile

from corpus import identity as I
from corpus import mapper as M


SRT = "1\n00:00:00,000 --> 00:00:10,000\nسلام\n\n2\n00:00:10,000 --> 00:00:20,000\nدنیا\n"


def _session(i, pid, link, filename, srt=None, status="subtitled",
             is_downloaded=1, is_subtitled=1,
             created_at=datetime.datetime(2024, 11, 8, 0, 0, 0),
             updated_at=datetime.datetime(2026, 1, 6, 12, 0, 0)):
    return {
        "id": i, "program_id": pid, "link": link,
        "created_at": created_at, "updated_at": updated_at,
        "filename": filename, "srt_filename": srt,
        "is_downloaded": is_downloaded, "status": status,
        "is_subtitled": is_subtitled, "attempts": 1, "last_error": None,
    }


def _link(ch, e):
    return "https://radio.iranseda.ir/epgarchivePart/?VALID=TRUE&ch=%d&e=%s" % (ch, e)


class FakeDB(object):
    """Minimal duck: fetch_sessions() + parse_ch/parse_e like corpus.database."""

    def __init__(self, sessions):
        self.sessions = sorted(sessions, key=lambda s: s["id"])

    def fetch_sessions(self, batch_size=1000, where=None, params=None):
        return len(self.sessions), iter(self.sessions)

    def fetch_programs(self):
        return []

    def fetch_llm_outputs(self, session_ids=None, where=None, params=None):
        return 0, iter([])

    def fetch_asr_outputs(self, session_ids=None):
        return []

    def fetch_crop_detections(self, session_ids=None):
        return []

    def table_counts(self):
        return {"radio_programs": 0, "radio_program_sessions": len(self.sessions),
                "llm_output": 0, "asr_output": 0, "crop_detection": 0}

    def high_watermark(self):
        return {"sessions_updated_at": "2026-01-06 12:00:00",
                "sessions_max_id": max(s["id"] for s in self.sessions),
                "llm_finished_at": "2026-01-06 10:05:00",
                "llm_max_id": 0}

    @staticmethod
    def parse_ch(url):
        from corpus import database as db
        return db.Database.parse_ch(url)

    @staticmethod
    def parse_e(url):
        from corpus import database as db
        return db.Database.parse_e(url)


class FakeDisk(object):
    """Minimal duck: find(relpath) -> abspath."""

    def __init__(self, mapping):
        self.mapping = mapping

    def find(self, relpath):
        return self.mapping.get(relpath)


def _disk(tmp, srt_names):
    d = os.path.join(tmp, "downloads")
    os.makedirs(d, exist_ok=True)
    mapping = {}
    for name in srt_names:
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(SRT)
        mapping["downloads/" + name] = p
    return FakeDisk(mapping)


def _one(tmp):
    """One program, one session — no collision, no groups."""
    s = [_session(1, 11, _link(14, "10000001"),
                  "radio-maaref-05-01-01-09-00.mp3",
                  srt="radio-maaref-05-01-01-09-00.srt")]
    return FakeDB(s)


# ----------------------------------------------------------------------
# 1. Distinct sessions cannot silently collapse.
# ----------------------------------------------------------------------
def test_distinct_sessions_do_not_collapse():
    s = [
        _session(1, 11, _link(14, "10000001"),
                 "radio-maaref-05-01-01-09-00.mp3",
                 srt="radio-maaref-05-01-01-09-00.srt"),
        _session(2, 12, _link(14, "10000001"),
                 "radio-maaref-05-02-01-09-00.mp3",
                 srt="radio-maaref-05-02-01-09-00.srt"),
    ]
    res = I.investigate(FakeDB(s), disk=None, log=lambda *a: None)
    assert res["summary"]["groups_total"] == 1
    g = res["groups"][0]
    assert g["member_count"] == 2
    assert g["session_ids"] == [1, 2]
    # both sessions preserved with distinct ids and distinct air dates
    # (stem radio-maaref-05-01-01-09-00 -> Jalali 1405-01-01 09:00;
    #  stem radio-maaref-05-02-01-09-00 -> Jalali 1405-02-01 09:00)
    assert g["broadcast_dates_jalali"] == ["1405-01-01", "1405-02-01"]


# ----------------------------------------------------------------------
# 2. Identical URLs do NOT automatically establish identical sessions.
# ----------------------------------------------------------------------
def test_identical_urls_do_not_equate_sessions():
    s = [
        _session(1, 11, _link(14, "10000001"),
                 "radio-maaref-05-01-01-09-00.mp3"),
        _session(2, 11, _link(14, "10000001"),
                 "radio-maaref-05-02-01-09-00.mp3"),
    ]
    res = I.investigate(FakeDB(s), disk=None, log=lambda *a: None)
    g = res["groups"][0]
    # same EPG slot reused for two air dates -> same program repeated,
    # NOT the same episode; the quarantine label is not "identical"
    assert g["category"] == I.CAT_SAME_PROGRAM_REPEATED_BROADCAST
    assert g["quarantine"]["policy"] == "PERMANENT_UNTIL_IDENTITY_PROVEN"
    # classification never implies identity: no episode_id is introduced
    for m in g["members"]:
        assert "episode_id" not in m


# ----------------------------------------------------------------------
# 3. Existing Class B records remain preserved (nothing dropped/merged).
# ----------------------------------------------------------------------
def test_class_b_members_all_preserved_with_ids():
    s = [
        _session(6217, 31, _link(14, "10000001"),
                 "radio-maaref-05-01-01-09-00.mp3", srt="a.srt"),
        _session(6218, 32, _link(14, "10000001"),
                 "radio-maaref-05-01-01-09-00.mp3", srt="a.srt"),
        _session(6219, 33, _link(14, "10000001"),
                 "radio-maaref-05-01-01-09-00.mp3", srt="a.srt"),
    ]
    res = I.investigate(FakeDB(s), disk=None, log=lambda *a: None)
    g = res["groups"][0]
    assert g["member_count"] == 3
    assert g["session_ids"] == [6217, 6218, 6219]
    assert g["program_ids"] == [31, 32, 33]
    # identical filenames across programs -> same episode, multiple refs
    assert g["category"] == I.CAT_SAME_EP_MULTI_REF
    assert g["quarantine"]["records_affected"] == 3
    # the investigation output is JSONL-safe (serializable, Persian-safe)
    blob = json.dumps(res, ensure_ascii=False)
    assert "session_id" in blob


# ----------------------------------------------------------------------
# 4. Exported record identifiers stay unique (the exporter's invariant
#    that Class B exists because of; investigation must not weaken it).
# ----------------------------------------------------------------------
def test_record_ids_unique_in_valid_corpus():
    from corpus import validator as V
    from corpus import exporter as E

    with tempfile.TemporaryDirectory() as tmp:
        downloads = os.path.join(tmp, "downloads")
        os.makedirs(os.path.join(downloads, "cleaned"), exist_ok=True)
        stem = "radio-maaref-05-01-01-09-00"
        # two sessions, SAME link (Class B), DIFFERENT filenames
        s = [
            _session(1, 11, _link(14, "10000001"), stem + ".mp3",
                     srt=stem + ".srt"),
            _session(2, 11, _link(14, "10000001"), stem + ".mp3"),
        ]
        with open(os.path.join(downloads, "cleaned", stem + ".srt"),
                  "w", encoding="utf-8") as f:
            f.write(SRT)

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
                return {k: v for k, v in self.__dict__.items()
                        if k != "db_pass"}

        from corpus import extractor as _ext
        db = FakeDB(s)
        disk = _ext.DiskIndex(downloads).scan()
        ex = E.Exporter(db, Cfg(), disk=disk, log=lambda *a: None)
        manifest = ex.run()
        assert manifest["records_written"] == 1
        assert manifest["records_invalid"] == 1
        with open(os.path.join(tmp, "out", "corpus.jsonl"),
                  encoding="utf-8") as f:
            rids = [json.loads(l)["record_id"] for l in f if l.strip()]
        assert len(rids) == len(set(rids)) == 1
        # invalid.jsonl kept the quarantined record with its DB id
        # (session identity lives in database_refs, not provenance)
        with open(os.path.join(tmp, "out", "invalid.jsonl"),
                  encoding="utf-8") as f:
            inv = [json.loads(l) for l in f if l.strip()]
        assert len(inv) == 1
        assert inv[0]["record"]["database_refs"]["session_id"] == 2
        assert any("duplicate record_id" in p for p in inv[0]["problems"])


# ----------------------------------------------------------------------
# 5. Quarantine information is reproducible (deterministic output).
# ----------------------------------------------------------------------
def test_investigation_deterministic():
    def _build():
        s = [
            _session(6217, 31, _link(14, "10000001"),
                     "radio-maaref-05-01-01-09-00.mp3", srt="a.srt"),
            _session(6218, 32, _link(14, "10000001"),
                     "radio-maaref-05-01-01-09-00.mp3", srt="a.srt"),
            _session(7000, 11, _link(14, "10000002"),
                     "radio-maaref-05-02-01-09-00.mp3", srt="b.srt"),
            _session(7001, 11, _link(14, "10000002"),
                     "radio-maaref-05-03-01-09-00.mp3", srt="c.srt"),
            _session(8000, 21, _link(9, "55"), "no-pattern-name.mp3"),
            _session(8001, 21, _link(9, "55"), "no-pattern-name.mp3"),
        ]
        return I.investigate(FakeDB(s), disk=None, log=lambda *a: None)

    r1, r2 = _build(), _build()
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)
    with tempfile.TemporaryDirectory() as tmp:
        p1 = os.path.join(tmp, "i1.jsonl")
        p2 = os.path.join(tmp, "i2.jsonl")
        I.write_jsonl(r1, p1)
        I.write_jsonl(r2, p2)
        assert open(p1, "rb").read() == open(p2, "rb").read()
    # stable group ordering by (ch, e): ch9:e55 before ch14 groups
    keys = [g["group_key"] for g in r1["groups"]]
    assert keys == ["ch9:e55", "ch14:e10000001", "ch14:e10000002"]
    # all five categories reachable; the no-filename pair is
    # same-episode (identical filenames) — deterministic rule
    cats = {g["group_key"]: g["category"] for g in r1["groups"]}
    assert cats["ch14:e10000001"] == I.CAT_SAME_EP_MULTI_REF
    assert cats["ch14:e10000002"] == I.CAT_SAME_PROGRAM_REPEATED_BROADCAST


# ----------------------------------------------------------------------
# 6. Repeated investigation -> identical results when source unchanged.
# ----------------------------------------------------------------------
def test_repeated_investigation_identical_with_disk():
    with tempfile.TemporaryDirectory() as tmp:
        disk = _disk(tmp, ["a.srt"])

        def _build():
            s = [
                _session(1, 11, _link(14, "10000001"),
                         "radio-maaref-05-01-01-09-00.mp3", srt="a.srt"),
                _session(2, 12, _link(14, "10000001"),
                         "radio-maaref-05-01-01-09-00.mp3", srt="a.srt"),
            ]
            return I.investigate(FakeDB(s), disk=disk,
                                 log=lambda *a: None)

        r1, r2 = _build(), _build()
        assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)
        g = r1["groups"][0]
        # SRT sha256s computed and equal across both members
        assert len(g["srt_sha256_distinct"]) == 1
        assert all(m["srt_sha256"] for m in g["members"])
        assert g["evidence"]["srt_content_identical"] is True


# ----------------------------------------------------------------------
# 7. classify_group pure-function invariants.
# ----------------------------------------------------------------------
def test_classify_group_pure_rules():
    m = lambda i, pid, fn: {"id": i, "program_id": pid, "filename": fn}
    # <2 members -> insufficient
    assert I.classify_group([m(1, 1, "a.mp3")]) == I.CAT_INSUFFICIENT_EVIDENCE
    assert I.classify_group([]) == I.CAT_INSUFFICIENT_EVIDENCE
    # identical filename, different programs -> same episode multi ref
    assert I.classify_group(
        [m(1, 1, "a.mp3"), m(2, 2, "a.mp3")]) == I.CAT_SAME_EP_MULTI_REF
    # same program, different air dates -> repeated broadcast
    assert I.classify_group(
        [m(1, 1, "radio-maaref-05-01-01-09-00.mp3"),
         m(2, 1, "radio-maaref-05-02-01-09-00.mp3")
         ]) == I.CAT_SAME_PROGRAM_REPEATED_BROADCAST
    # different programs, same air date -> shared archive reference
    # (distinct filenames — an identical filename would be classified as
    #  same-episode-multiple-references, the more decisive rule)
    assert I.classify_group(
        [m(1, 1, "radio-maaref-05-01-01-09-00.mp3"),
         m(2, 2, "radio-khayam-05-01-01-09-00.mp3")
         ]) == I.CAT_DIFF_PROGRAM_SHARED_ARCHIVE
    # different programs, different air dates -> still shared archive
    assert I.classify_group(
        [m(1, 1, "radio-maaref-05-01-01-09-00.mp3"),
         m(2, 2, "radio-maaref-05-02-01-09-00.mp3")
         ]) == I.CAT_DIFF_PROGRAM_SHARED_ARCHIVE
    # no filenames at all -> insufficient evidence
    assert I.classify_group(
        [m(1, 1, None), m(2, 2, None)
         ]) == I.CAT_INSUFFICIENT_EVIDENCE


# ----------------------------------------------------------------------
# 8. write_jsonl shape: summary first, one line per group, stable.
# ----------------------------------------------------------------------
def test_write_jsonl_shape():
    s = [
        _session(1, 11, _link(14, "10000001"),
                 "radio-maaref-05-01-01-09-00.mp3", srt="a.srt"),
        _session(2, 12, _link(14, "10000001"),
                 "radio-maaref-05-01-01-09-00.mp3", srt="a.srt"),
    ]
    res = I.investigate(FakeDB(s), disk=None, log=lambda *a: None)
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "class_b_investigation.jsonl")
        I.write_jsonl(res, p)
        with open(p, encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
    assert lines[0]["investigation_version"] == I.INVESTIGATION_VERSION
    assert lines[0]["groups_total"] == 1
    assert lines[1]["group_key"] == "ch14:e10000001"
    assert lines[1]["record_id"] == "iranseda:ch14:e10000001"
    assert lines[1]["quarantine"]["policy"] == "PERMANENT_UNTIL_IDENTITY_PROVEN"
