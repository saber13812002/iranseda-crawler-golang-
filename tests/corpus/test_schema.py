"""Stage 2 — versioned corpus schema: loader + verification (no DB)."""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from corpus import schema as S  # noqa: E402
from corpus import validator as V  # noqa: E402


def test_verify_passes_clean():
    """Schema + field mapping + examples are all consistent."""
    problems = S.verify()
    assert problems == [], problems


def test_schema_metadata_and_contract():
    sch = S.load_schema()
    assert sch["$schema"] == S.DRAFT_2020_12
    assert isinstance(sch["$id"], str) and sch["$id"]
    meta = sch["x-corpus"]
    assert meta["schema_version"] == "1.0"
    assert meta["identity_policy"] == "PERMANENT_UNTIL_IDENTITY_PROVEN"
    # versioned required set = validator's REQUIRED_TOP + speakers
    # (validator reads rec["speakers"] directly, so it is de-facto required)
    assert set(sch["required"]) == set(V.REQUIRED_TOP) | {"speakers"}
    # Stage 1 annotations present
    assert "stage 1" in sch["description"].lower()
    assert "authoritative" in sch["properties"]["database_refs"]["description"].lower()
    # artifact $def present
    assert "artifact" in sch["$defs"]


def test_field_mapping_covers_all_fields():
    fm = S.load_field_mapping()
    assert fm["version"] == "1.0"
    for s in S.MAPPING_STATUSES:
        assert s in fm["legend"], s
    assert fm["fields"], "no field entries"
    # every top-level property covered by at least one entry
    covered = set()
    for f in fm["fields"]:
        fld = f.get("field") or ""
        for top in S.REQUIRED_TOP_COVERAGE:
            if fld == top or fld.startswith(top + "."):
                covered.add(top)
    missing = set(S.REQUIRED_TOP_COVERAGE) - covered
    assert not missing, missing
    # statuses are declared; available/derivable always carry a source
    for f in fm["fields"]:
        if f["field"].startswith("table:"):
            assert f["status"] == "not_applicable", f["field"]
            continue
        assert f["status"] in S.MAPPING_STATUSES, f["field"]
        assert f.get("rule") is not None, f["field"]
        if f["status"] in ("available", "derivable") and \
                f.get("source_type") in ("db", "disk"):
            assert f.get("source"), f["field"]
    # the honest gaps are declared, never hidden
    by_field = {f["field"]: f for f in fm["fields"]}
    assert by_field["speakers.items"]["status"] == "missing"
    assert by_field["transcripts.whisper_provenance"]["status"] == "unverified"
    assert by_field["broadcast"]["status"] == "derivable"
    # broadcast must NOT be derived from created_at (crawl/insert time);
    # the mapping names sessions.filename as the source and the rule must
    # explicitly forbid created_at.
    assert "created_at" not in (by_field["broadcast"].get("source") or "")
    assert "filename" in (by_field["broadcast"].get("source") or "")
    assert "created_at" in (by_field["broadcast"].get("rule") or "").lower()
    assert "never" in (by_field["broadcast"].get("rule") or "").lower()


def test_examples_present_and_named():
    names = S.list_examples()
    assert "valid_record.json" in names
    assert "quarantine_record.json" in names


def test_valid_example_passes_validator():
    rec = S.load_example("valid_record.json")
    probs = V.validate_record(rec)
    assert probs == [], probs
    # the example embodies the time/calendar contract
    b = rec["broadcast"]
    assert b["jalali"]["date"] == "1405-01-01"
    assert b["jalali"]["source"] == "filename"
    assert b["gregorian"]["date"] == "2026-03-21"
    assert b["gregorian"]["source"] == "derived_from_jalali_filename"
    assert b["filename_stem"] == "radio-maaref-05-01-01-09-00"
    assert rec["quality"]["text_normalized"] == "NFC"
    # original and corrected are independent entries (original kept)
    assert rec["transcripts"]["originals"]["srt"]["exists"] is True
    lo = rec["transcripts"]["llm_outputs"][0]
    assert lo["job_type"] == "correct_subtitles"
    assert V.srtmod.looks_like_srt(lo["srt_content"]) if hasattr(V, "srtmod") else True


def test_quarantine_example_shape():
    ex = S.load_example("quarantine_record.json")
    rec = ex["record"]
    # the record itself is structurally valid (quarantine is a batch-level
    # identity decision, not a structural one)
    probs = V.validate_record(rec)
    assert probs == [], probs
    assert isinstance(ex["problems"], list) and ex["problems"]
    assert any("duplicate record_id" in p for p in ex["problems"]), ex["problems"]
    # identity policy stated on the record
    assert any("PERMANENT_UNTIL_IDENTITY_PROVEN" in w
               for w in rec["quality"]["warnings"]), rec["quality"]["warnings"]
    # session_id is the authoritative identity (Stage 1)
    assert rec["database_refs"]["session_id"] == 6217


def test_verify_rejects_bad_example():
    """verify() flags unreadable / invalid example files (drift gate)."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        bad = os.path.join(tmp, "broken.json")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("{ not json")
        problems = S.verify(examples=["broken.json"])
        assert any("examples/broken.json" in p for p in problems), problems
        # a well-formed but contract-violating record is also flagged
        viol = dict(S.load_example("valid_record.json"))
        viol["quality"]["text_normalized"] = "NFD"
        bad2 = os.path.join(tmp, "violating.json")
        with open(bad2, "w", encoding="utf-8") as f:
            json.dump(viol, f, ensure_ascii=False)
        problems2 = S.verify(examples=["violating.json"])
        assert any("examples/violating.json" in p for p in problems2), problems2
