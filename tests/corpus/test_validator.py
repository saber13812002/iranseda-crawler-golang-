"""Validator: structural + mission-rule checks (positive & negative)."""

import copy
import datetime

from corpus import validator as V

BASE_SRT = "1\n00:00:00,000 --> 00:00:10,000\nسلام\n"
BASE_CORR = "1\n0:00:00 --> 0:00:10\nسلام\n"


def _rec(**over):
    r = {
        "schema_version": "1.0",
        "record_id": "iranseda:ch14:e152507883",
        "episode_key": {"ch": 14, "e": "152507883", "m": "044116", "source": "link"},
        "database_refs": {
            "session_id": 1,
            "program_id": 11,
            "program_ids_all": [11],
            "tables": {
                "radio_program_sessions": 1,
                "radio_programs": [11],
                "llm_output": [900],
                "crop_detection": None,
                "asr_output": [],
            },
        },
        "program": {
            "name": "برنامه",
            "name_raw": "برنامه",
            "url": "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=044116",
            "ch": 14,
            "m": "044116",
            "radio": "معارف",
            "description": None,
            "schedule": {
                "start_time": "09:00:00",
                "description_raw": None,
                "description_normalized": None,
                "source": "programs.time",
            },
            "crop": None,
        },
        "broadcast": {
            "jalali": {"date": "1405-01-01", "time": "09:00:00", "source": "filename"},
            "gregorian": {"date": "2026-03-21", "time": "09:00:00",
                          "source": "derived_from_jalali_filename",
                          "conversion": "test"},
            "filename_stem": "radio-maaref-05-01-01-09-00",
        },
        "audio": {
            "url": "https://radio.iranseda.ir/epgarchivePart/?VALID=TRUE&ch=14&e=1",
            "link_raw": "../epgarchivePart/?VALID=TRUE&ch=14&e=1",
            "filename": "radio-maaref-05-01-01-09-00.mp3",
            "local_exists": True,
        },
        "speakers": {"items": [], "missing_reason": "no verified source"},
        "transcripts": {
            "originals": {
                "srt": {"exists": True, "db_filename": "a.srt",
                        "relpath": "downloads/cleaned/a.srt",
                        "content": BASE_SRT, "sha256": "x",
                        "char_count": len(BASE_SRT), "segment_count": 1,
                        "duration_sec": 10.0, "missing_reason": None},
                "txt": {"exists": True, "db_filename": None,
                        "relpath": "downloads/cleaned/a.txt",
                        "content": "سلام", "sha256": "y",
                        "char_count": 3, "segment_count": None,
                        "duration_sec": None, "missing_reason": None},
            },
            "llm_outputs": [{
                "llm_output_id": 900,
                "job_type": "correct_subtitles",
                "model": "qwen38-nothinking",
                "prompt_id": 3,
                "status": "done",
                "content": None,
                "content_en": None,
                "srt_content": BASE_CORR,
                "file_relpath": "downloads/cleaned/a.correct.srt",
                "disk_exists": True,
                "input_tokens": 1,
                "output_tokens": 1,
                "started_at": "2026-01-01 00:00:00",
                "finished_at": "2026-01-01 00:00:01",
            }],
            "asr_outputs": [],
            "whisper_provenance": {"provider": "whisper (...)", "details_available": False},
        },
        "crop": None,
        "source_metadata": {
            "episode_url": "https://radio.iranseda.ir/epgarchivePart/?VALID=TRUE&ch=14&e=1",
            "program_url": "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=044116",
            "site_base": "https://radio.iranseda.ir/",
        },
        "pipeline_state": {"status": "subtitled", "is_downloaded": True,
                           "attempts": 1, "last_error": None},
        "provenance": {
            "exported_at": "2026-01-07 00:00:00",
            "export_version": "test",
            "sources": ["radio_program_sessions#1"],
            "session_created_at": "2024-11-08 00:00:00",
            "session_updated_at": "2026-01-06 00:00:00",
        },
        "quality": {"missing": [], "warnings": [], "text_normalized": "NFC"},
    }
    r.update(over)
    return r


def test_valid_record_passes():
    assert V.validate_record(_rec(), seen_ids=set()) == []


def test_missing_required_key():
    r = _rec()
    del r["quality"]
    probs = V.validate_record(r)
    assert any(p.startswith("quality:") for p in probs)


def test_bad_record_id_pattern():
    probs = V.validate_record(_rec(record_id="iranseda:ch14e1"))
    assert any("record_id" in p for p in probs)


def test_duplicate_record_id_in_batch():
    r1 = _rec()
    r2 = _rec()
    seen = set()
    V.validate_record(r1, seen_ids=seen)
    probs = V.validate_record(r2, seen_ids=seen)
    assert any("duplicate" in p for p in probs)


def test_broadcast_gregorian_must_match_jalali():
    r = _rec()
    r["broadcast"]["gregorian"]["date"] = "2020-01-01"  # wrong
    probs = V.validate_record(r)
    assert any("does not match jalali" in p for p in probs)


def test_broadcast_null_is_allowed_with_missing():
    r = _rec(broadcast=None)
    r["quality"]["missing"] = ["broadcast.date"]
    assert V.validate_record(r) == []


def test_corrected_srt_must_parse():
    r = _rec()
    r["transcripts"]["llm_outputs"][0]["srt_content"] = "not an srt"
    probs = V.validate_record(r)
    assert any("corrected SRT does not parse" in p for p in probs)


def test_original_srt_content_must_parse():
    r = _rec()
    r["transcripts"]["originals"]["srt"]["content"] = "garbage"
    probs = V.validate_record(r)
    assert any("originals.srt" in p and "parse" in p for p in probs)


def test_private_path_leak_detected():
    r = _rec()
    r["transcripts"]["originals"]["srt"]["relpath"] = "/home/saber/x.srt"
    probs = V.validate_record(r)
    assert any("private path" in p for p in probs)


def test_secret_leak_detected():
    r = _rec()
    r["program"]["description"] = "token=sk-abcdef1234567890abcdef"
    probs = V.validate_record(r)
    assert any("secret" in p for p in probs)


def test_bad_job_type_enum():
    # escape valve: unknown job-type STRINGS pass (mapper warns); a
    # missing / non-string job_type is a validation failure.
    r = _rec()
    r["transcripts"]["llm_outputs"][0]["job_type"] = None
    probs = V.validate_record(r)
    assert any("job_type" in p for p in probs)


def test_text_normalized_must_be_nfc():
    probs = V.validate_record(_rec(
        quality={"missing": [], "warnings": [], "text_normalized": "NFD"}))
    assert any("text_normalized" in p for p in probs)


def test_episode_key_link_requires_ch_e():
    r = _rec()
    r["episode_key"]["ch"] = None
    probs = V.validate_record(r)
    assert any("link source" in p for p in probs)


def test_fallback_key_valid_shape():
    r = _rec(record_id="iranseda:db11:s123",
             episode_key={"ch": None, "e": None, "m": "044116",
                          "source": "fallback_db"})
    assert V.validate_record(r) == []


def test_validate_batch_counts():
    recs = [_rec(), _rec(record_id="iranseda:ch14:e2")]
    problems, ok = V.validate_batch(recs)
    assert ok == 2 and not problems
    recs2 = [_rec(), _rec()]  # dup id
    problems, ok = V.validate_batch(recs2)
    assert ok == 1 and len(problems) == 1
