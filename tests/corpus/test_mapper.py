"""Mapper: synthetic DB + fake disk -> record contract compliance.

Covers the mission §4 rules: identity, broadcast from filename (not
created_at), original+corrected both kept, nulls + missing status,
canonical URLs, no server-private paths, NFC, schedule != episode time,
speakers empty-with-reason.
"""

import datetime
import os
import tempfile

from corpus import mapper, config as _config, extractor as _extractor
from corpus import validator as V

SITE = "https://radio.iranseda.ir/"


class FakeCfg(object):
    root = "/tmp/fake-root"
    downloads_dir = "/tmp/fake-root/downloads"
    out_dir = "/tmp/fake-out"
    db_host = "127.0.0.1"
    db_port = 3308
    db_user = "u"
    db_pass = "p"
    db_name = "iranseda"
    inline_originals = True
    inline_llm = True
    shard_lines = 0
    incremental_hours = 6.0
    overlap_hours = 12.0
    export_enabled = False
    site_base = SITE


ORIGINAL_SRT = "1\n00:00:00,000 --> 00:00:10,000\nسلام\n\n2\n00:00:10,000 --> 00:00:20,000\nدنیا\n"
CORRECT_SRT = "1\n0:00:00 --> 0:00:10\nسلام و درود\n"


def _make_disk(tmp, files):
    for rel, content in files.items():
        p = os.path.join(tmp, rel)
        d = os.path.dirname(p)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
    # DiskIndex base must be the directory that CONTAINS downloads/ (i.e. the
    # project root); files here are written under <tmp>/downloads/...
    return _extractor.DiskIndex(os.path.join(tmp, "downloads")).scan()


def _session(**over):
    s = {
        "id": 123,
        "program_id": 11,
        "link": "../epgarchivePart/?VALID=TRUE&ch=14&e=152507883",
        "created_at": datetime.datetime(2026, 1, 5, 12, 0, 0),
        "updated_at": datetime.datetime(2026, 1, 6, 12, 0, 0),
        "filename": "radio-maaref-04-01-01-09-00.mp3",
        "srt_filename": "radio-maaref-04-01-01-09-00.srt",
        "is_downloaded": 1,
        "status": "subtitled",
        "is_subtitled": 1,
        "attempts": 1,
        "last_error": None,
    }
    if "srt" in over:
        s["srt_filename"] = over.pop("srt")
    s.update(over)
    return s


def _program():
    return {
        "id": 11,
        "name": "برنامهٔ\n\tصبح",
        "url": "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=044116",
        # pymysql returns the live TIME column as timedelta — keep the fake
        # faithful to production (this is what crashed the 2026-11-04 pilot).
        "time": datetime.timedelta(hours=9),
        "time_description": "هر روز صبح",
        "description": "desc",
        "created_at": datetime.datetime(2024, 11, 8, 0, 0, 0),
        "start": None,
        "radio": "معارف",
        "radio_id": None,
        "is_legacy": 0,
        "legacy_expires_at": None,
        "crop_offset": None,
        "crop_enabled": None,
        "crop_auto": None,
    }


def _llm_row(**over):
    r = {
        "id": 900,
        "session_id": 123,
        "job_type": "correct_subtitles",
        "model": "qwen38-nothinking",
        "prompt_id": 3,
        "job_id": None,
        "content": None,
        "content_en": None,
        "srt_content": CORRECT_SRT,
        "file_relpath": "downloads/cleaned/radio-maaref-04-01-01-09-00.correct.srt",
        "started_at": datetime.datetime(2026, 1, 6, 10, 0, 0),
        "finished_at": datetime.datetime(2026, 1, 6, 10, 5, 0),
        "status": "done",
        "error": None,
        "input_tokens": 100,
        "output_tokens": 50,
    }
    r.update(over)
    return r


def _build(session, prog, llm, disk, tmp, asr=None, crop=None):
    prog_by_id = {11: prog}
    prog_by_chm = {(14, "044116"): [11]}
    rec = mapper.build_record(
        session, prog_by_id, prog_by_chm, llm, asr or [], crop,
        disk, FakeCfg(), "test-run", "2026-01-07 00:00:00")
    return rec


def test_identity_from_link():
    with tempfile.TemporaryDirectory() as tmp:
        disk = _make_disk(tmp, {
            "downloads/radio-maaref-04-01-01-09-00.mp3": "x",
            "downloads/cleaned/radio-maaref-04-01-01-09-00.srt": ORIGINAL_SRT,
            "downloads/cleaned/radio-maaref-04-01-01-09-00.txt": "سلام\n",
        })
        rec = _build(_session(), _program(), [_llm_row()], disk, tmp)
    assert rec["record_id"] == "iranseda:ch14:e152507883"
    assert rec["episode_key"]["source"] == "link"
    assert rec["episode_key"]["ch"] == 14
    assert rec["episode_key"]["e"] == "152507883"
    assert rec["episode_key"]["m"] == "044116"
    assert rec["database_refs"]["session_id"] == 123
    assert rec["database_refs"]["tables"]["llm_output"] == [900]


def test_identity_fallback_db():
    with tempfile.TemporaryDirectory() as tmp:
        disk = _make_disk(tmp, {})
        rec = _build(_session(link=None, program_id=11, id=555),
                     _program(), [], disk, tmp)
    assert rec["record_id"] == "iranseda:db11:s555"
    assert rec["episode_key"]["source"] == "fallback_db"
    assert rec["quality"]["warnings"] and \
        any("fallback_db" in w for w in rec["quality"]["warnings"])


def test_broadcast_from_filename_not_created_at():
    with tempfile.TemporaryDirectory() as tmp:
        disk = _make_disk(tmp, {})
        # created_at is Jan 2026 (crawl) but filename says Jalali 1404-01-01
        rec = _build(_session(), _program(), [], disk, tmp)
    b = rec["broadcast"]
    assert b["jalali"]["date"] == "1404-01-01"
    assert b["jalali"]["time"] == "09:00:00"
    assert b["jalali"]["source"] == "filename"
    assert b["gregorian"]["source"] == "derived_from_jalali_filename"
    # 1404-01-01 Jalali = 2025-03-20 Gregorian (nowruz 1404 -> 2025-03-21? verify:
    # 1404 %33 = 26 -> leap; nowruz 1404 = 2025-03-21 per anchor table)
    assert b["gregorian"]["date"] == "2025-03-21"
    assert b["filename_stem"] == "radio-maaref-04-01-01-09-00"


def test_broadcast_null_when_no_filename():
    with tempfile.TemporaryDirectory() as tmp:
        disk = _make_disk(tmp, {})
        rec = _build(_session(filename=None, srt_filename=None), _program(), [], disk, tmp)
    assert rec["broadcast"] is None
    assert "broadcast.date" in rec["quality"]["missing"]


def test_original_and_corrected_both_kept():
    with tempfile.TemporaryDirectory() as tmp:
        disk = _make_disk(tmp, {
            "downloads/cleaned/radio-maaref-04-01-01-09-00.srt": ORIGINAL_SRT,
            "downloads/cleaned/radio-maaref-04-01-01-09-00.txt": "سلام\n",
            "downloads/cleaned/radio-maaref-04-01-01-09-00.correct.srt": CORRECT_SRT,
        })
        llm = [_llm_row(),
               _llm_row(id=901, job_type="correct_text", srt_content=None,
                        content="متن تصحیح‌شده",
                        file_relpath="downloads/cleaned/radio-maaref-04-01-01-09-00.correct.txt")]
        rec = _build(_session(), _program(), llm, disk, tmp)
    orig = rec["transcripts"]["originals"]
    assert orig["srt"]["exists"] is True
    assert orig["srt"]["content"] is not None
    assert orig["srt"]["segment_count"] == 2
    assert orig["srt"]["duration_sec"] == 20.0
    assert orig["txt"]["exists"] is True
    assert len(rec["transcripts"]["llm_outputs"]) == 2
    cs = [x for x in rec["transcripts"]["llm_outputs"]
          if x["job_type"] == "correct_subtitles"][0]
    assert cs["srt_content"].startswith("1\n0:00:00")
    assert cs["disk_exists"] is True
    ct = [x for x in rec["transcripts"]["llm_outputs"]
          if x["job_type"] == "correct_text"][0]
    assert ct["content"] == "متن تصحیح‌شده"
    # original content preserved even though a corrected version exists
    assert "سلام" in orig["srt"]["content"]


def test_schedule_is_program_not_episode():
    with tempfile.TemporaryDirectory() as tmp:
        disk = _make_disk(tmp, {})
        rec = _build(_session(), _program(), [], disk, tmp)
    sch = rec["program"]["schedule"]
    assert sch["start_time"] == "09:00:00"
    assert sch["source"] == "programs.time"
    # episode time comes from broadcast, not schedule
    assert rec["broadcast"]["jalali"]["time"] == "09:00:00"
    assert rec["program"]["schedule"] is not None


def test_program_normalization_with_raw():
    with tempfile.TemporaryDirectory() as tmp:
        disk = _make_disk(tmp, {})
        rec = _build(_session(), _program(), [], disk, tmp)
    assert rec["program"]["name"] == "برنامهٔ صبح"
    assert rec["program"]["name_raw"] == "برنامهٔ\n\tصبح"
    assert rec["program"]["url"].endswith("ch=14&m=044116")
    assert rec["program"]["ch"] == 14
    assert rec["program"]["m"] == "044116"


def test_legacy_merge_warning():
    with tempfile.TemporaryDirectory() as tmp:
        disk = _make_disk(tmp, {})
        prog2 = dict(_program())
        prog2["id"] = 12
        prog2["is_legacy"] = 1
        prog2["name"] = "old name"
        prog_by_id = {11: _program(), 12: prog2}
        prog_by_chm = {(14, "044116"): [11, 12]}
        rec = mapper.build_record(
            _session(), prog_by_id, prog_by_chm, [], [], None,
            disk, FakeCfg(), "t", "2026-01-07 00:00:00")
    assert rec["database_refs"]["program_ids_all"] == [11, 12]
    assert "legacy_program_duplicate_merged" in rec["quality"]["warnings"]
    assert rec["program"]["name"] == "برنامهٔ صبح"  # non-legacy preferred


def test_speakers_empty_with_reason():
    with tempfile.TemporaryDirectory() as tmp:
        disk = _make_disk(tmp, {})
        rec = _build(_session(), _program(), [], disk, tmp)
    assert rec["speakers"]["items"] == []
    assert rec["speakers"]["missing_reason"]


def test_audio_url_absolute_and_local_exists():
    with tempfile.TemporaryDirectory() as tmp:
        disk = _make_disk(tmp, {
            "downloads/radio-maaref-04-01-01-09-00.mp3": "x",
        })
        rec = _build(_session(), _program(), [], disk, tmp)
    assert rec["audio"]["url"] == \
        "https://radio.iranseda.ir/epgarchivePart/?VALID=TRUE&ch=14&e=152507883"
    assert rec["audio"]["local_exists"] is True
    assert rec["source_metadata"]["episode_url"] == rec["audio"]["url"]
    assert rec["source_metadata"]["site_base"] == SITE


def test_no_private_paths_in_record():
    import json as _json
    with tempfile.TemporaryDirectory() as tmp:
        disk = _make_disk(tmp, {})
        rec = _build(_session(), _program(), [_llm_row()], disk, tmp)
    blob = _json.dumps(rec, ensure_ascii=False)
    assert "/home/" not in blob
    assert "/tmp/fake" not in blob  # absolute disk paths never embedded


def test_missing_tracked_for_llm_disk():
    with tempfile.TemporaryDirectory() as tmp:
        disk = _make_disk(tmp, {})  # no corrected file on disk
        llm = [_llm_row(file_relpath="downloads/cleaned/nope.correct.srt")]
        rec = _build(_session(), _program(), llm, disk, tmp)
    cs = rec["transcripts"]["llm_outputs"][0]
    assert cs["disk_exists"] is False
    assert any(x.startswith("llm_output.correct_subtitles.disk:")
               for x in rec["quality"]["missing"])


def test_unknown_job_type_warns_not_fails():
    with tempfile.TemporaryDirectory() as tmp:
        disk = _make_disk(tmp, {})
        llm = [_llm_row(job_type="future_thing", srt_content=None,
                        file_relpath=None)]
        rec = _build(_session(), _program(), llm, disk, tmp)
    assert rec["transcripts"]["llm_outputs"][0]["job_type"] == "future_thing"
    assert any(w.startswith("unknown_job_type:") for w in rec["quality"]["warnings"])


def test_program_missing_tracked():
    with tempfile.TemporaryDirectory() as tmp:
        disk = _make_disk(tmp, {})
        rec = _build(_session(program_id=999), {}, [], disk, tmp)
    assert "program" in rec["quality"]["missing"]
    assert rec["database_refs"]["program_id"] == 999


def test_record_passes_validator():
    with tempfile.TemporaryDirectory() as tmp:
        disk = _make_disk(tmp, {
            "downloads/cleaned/radio-maaref-04-01-01-09-00.srt": ORIGINAL_SRT,
            "downloads/cleaned/radio-maaref-04-01-01-09-00.txt": "سلام\n",
            "downloads/cleaned/radio-maaref-04-01-01-09-00.correct.srt": CORRECT_SRT,
        })
        rec = _build(_session(), _program(), [_llm_row()], disk, tmp)
    probs = V.validate_record(rec, seen_ids=set())
    assert probs == [], probs


def test_deterministic_fingerprint():
    with tempfile.TemporaryDirectory() as tmp:
        disk = _make_disk(tmp, {})
        rec1 = _build(_session(), _program(), [], disk, tmp)
        rec2 = _build(_session(), _program(), [], disk, tmp)
    assert mapper.record_fingerprint(rec1) == mapper.record_fingerprint(rec2)
    # volatile provenance excluded:
    rec2["provenance"]["exported_at"] = "9999-01-01 00:00:00"
    assert mapper.record_fingerprint(rec1) == mapper.record_fingerprint(rec2)
