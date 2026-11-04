"""Structural record validator (pure stdlib — no jsonschema dependency).

Validates corpus records against the v1 contract WITHOUT the jsonschema
library (53's venv lacks it). It enforces the same structural rules as
schemas/iranseda-corpus-v1.schema.json plus the mission §4 rules:

  * required top-level keys, types, enums, patterns
  * record_id pattern + uniqueness (batch level)
  * original never replaced: if a corrected SRT exists the original
    SRT must still be its own artifact entry (checked by caller with
    the record's artifacts)
  * SRT content (original + corrected) must parse with valid cues
  * broadcast: jalali+gregorian separate with sources, or null+missing
  * no server-private paths anywhere in the record (/home/, /root/,
    C:\\)
  * no secrets (token/password/api key patterns in string fields)
  * quality.text_normalized == "NFC"
"""

import os
import re
import json

from . import srt as srtmod

REQUIRED_TOP = (
    "schema_version", "record_id", "episode_key", "database_refs",
    "program", "audio", "transcripts", "provenance", "quality",
)

RECORD_ID_RE = re.compile(r"^iranseda:(ch[0-9]+:e[0-9]+|db[0-9]+:s[0-9]+)$")
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
TIME_RE = re.compile(r"^[0-9]{2}:[0-9]{2}:[0-9]{2}$")
JOB_TYPES = ("correct_subtitles", "correct_text", "summary", "full_text", "qa")

SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*\S+"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"hf_[A-Za-z0-9]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{16,}"),
)

PRIVATE_PATH_RE = re.compile(r"(/home/|/root/|/var/www/|C:\\\\|C:/Users)")


def _type_ok(value, allowed):
    """allowed: tuple of python types or the literals 'str', 'num'..."""
    for a in allowed:
        if a is None and value is None:
            return True
        if a is bool:
            if isinstance(value, bool):
                return True
        elif a is int:
            if isinstance(value, int) and not isinstance(value, bool):
                return True
        elif a is float:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return True
        elif a is str:
            if isinstance(value, str):
                return True
        elif a is dict:
            if isinstance(value, dict):
                return True
        elif a is list:
            if isinstance(value, list):
                return True
    return False


def _err(rec, problems, path, msg):
    problems.append("%s: %s" % (path, msg))


def validate_record(rec, seen_ids=None):
    """Validate one record. Returns list of problem strings (empty=valid)."""
    p = []
    if not isinstance(rec, dict):
        return ["record: not a dict"]

    for k in REQUIRED_TOP:
        if k not in rec:
            _err(rec, p, k, "missing required key")
    if p:
        return p

    if rec["schema_version"] != "1.0":
        _err(rec, p, "schema_version", "must be '1.0'")

    rid = rec["record_id"]
    if not isinstance(rid, str) or not RECORD_ID_RE.match(rid):
        _err(rec, p, "record_id", "bad pattern: %r" % (rid,))
    if seen_ids is not None:
        if rid in seen_ids:
            _err(rec, p, "record_id", "duplicate record_id in batch: %s" % rid)
        seen_ids.add(rid)

    ek = rec["episode_key"]
    if not _type_ok(ek, (dict,)):
        _err(rec, p, "episode_key", "must be object")
    else:
        if "source" not in ek:
            _err(rec, p, "episode_key.source", "missing")
        elif ek["source"] not in ("link", "fallback_db"):
            _err(rec, p, "episode_key.source", "bad enum %r" % ek["source"])
        if ek["source"] == "link":
            if not _type_ok(ek.get("ch"), (int,)) or not _type_ok(ek.get("e"), (str,)):
                _err(rec, p, "episode_key", "link source requires int ch + str e")
        if "m" in ek and ek["m"] is not None and not _type_ok(ek["m"], (str,)):
            _err(rec, p, "episode_key.m", "must be string")

    dr = rec["database_refs"]
    if not _type_ok(dr, (dict,)):
        _err(rec, p, "database_refs", "must be object")
    else:
        for k in ("session_id", "program_id", "tables"):
            if k not in dr:
                _err(rec, p, "database_refs.%s" % k, "missing")
        if not _type_ok(dr.get("session_id"), (int,)):
            _err(rec, p, "database_refs.session_id", "must be int")
        tables = dr.get("tables")
        if not _type_ok(tables, (dict,)):
            _err(rec, p, "database_refs.tables", "must be object")
        else:
            if "radio_program_sessions" not in tables or "radio_programs" not in tables:
                _err(rec, p, "database_refs.tables", "missing required subkeys")

    prog = rec["program"]
    if not _type_ok(prog, (dict,)):
        _err(rec, p, "program", "must be object")
    else:
        for k in ("name", "url"):
            if k not in prog or not isinstance(prog[k], str):
                _err(rec, p, "program.%s" % k, "missing/invalid")
        if prog.get("schedule") is not None:
            sch = prog["schedule"]
            if not _type_ok(sch, (dict,)):
                _err(rec, p, "program.schedule", "must be object")
            else:
                if sch.get("source") not in ("programs.time",
                                             "programs.time_description", "none"):
                    _err(rec, p, "program.schedule.source", "bad enum")
                if sch.get("start_time") is not None and not TIME_RE.match(sch["start_time"]):
                    _err(rec, p, "program.schedule.start_time", "bad HH:MM:SS")

    b = rec["broadcast"]
    if b is not None:
        if not _type_ok(b, (dict,)):
            _err(rec, p, "broadcast", "must be object or null")
        else:
            j = b.get("jalali")
            g = b.get("gregorian")
            if not _type_ok(j, (dict,)):
                _err(rec, p, "broadcast.jalali", "must be object")
            else:
                if not _type_ok(j.get("date"), (str,)) or not DATE_RE.match(j.get("date") or ""):
                    _err(rec, p, "broadcast.jalali.date", "bad YYYY-MM-DD")
                if j.get("time") is not None and not TIME_RE.match(j.get("time") or ""):
                    _err(rec, p, "broadcast.jalali.time", "bad HH:MM:SS")
                if j.get("source") != "filename":
                    _err(rec, p, "broadcast.jalali.source", "must be 'filename'")
            if g is not None:
                if not _type_ok(g, (dict,)):
                    _err(rec, p, "broadcast.gregorian", "must be object")
                else:
                    if g.get("date") is not None and not DATE_RE.match(g.get("date") or ""):
                        _err(rec, p, "broadcast.gregorian.date", "bad YYYY-MM-DD")
                    if g.get("source") != "derived_from_jalali_filename":
                        _err(rec, p, "broadcast.gregorian.source", "bad const")
            # cross-check: jalali and gregorian must agree (recompute)
            if _type_ok(j, (dict,)) and _type_ok(j.get("date"), (str,)) and j.get("date"):
                if _type_ok(g, (dict,)) and _type_ok(g.get("date"), (str,)) and g.get("date"):
                    from . import jalali
                    yy, mm, dd = (int(x) for x in j["date"].split("-"))
                    gy, gm, gd = jalali.jalali_to_gregorian(yy, mm, dd)
                    expect = "%04d-%02d-%02d" % (gy, gm, gd)
                    if g["date"] != expect:
                        _err(rec, p, "broadcast.gregorian.date",
                             "does not match jalali (expect %s)" % expect)

    au = rec["audio"]
    if not _type_ok(au, (dict,)):
        _err(rec, p, "audio", "must be object")
    else:
        if not _type_ok(au.get("url"), (str,)) or not au["url"]:
            _err(rec, p, "audio.url", "must be non-empty string")

    sp = rec["speakers"]
    if not _type_ok(sp, (dict,)):
        _err(rec, p, "speakers", "must be object")
    else:
        if not _type_ok(sp.get("items"), (list,)):
            _err(rec, p, "speakers.items", "must be list")
        if not _type_ok(sp.get("missing_reason"), (str,)):
            _err(rec, p, "speakers.missing_reason", "must be string")

    tr = rec["transcripts"]
    if not _type_ok(tr, (dict,)):
        _err(rec, p, "transcripts", "must be object")
    else:
        for k in ("originals", "llm_outputs", "asr_outputs"):
            if k not in tr:
                _err(rec, p, "transcripts.%s" % k, "missing")
        orig = tr.get("originals")
        if not _type_ok(orig, (dict,)):
            _err(rec, p, "transcripts.originals", "must be object")
        else:
            for k in ("srt", "txt"):
                art = orig.get(k)
                if not _type_ok(art, (dict,)):
                    _err(rec, p, "transcripts.originals.%s" % k, "must be object")
                else:
                    _check_artifact(p, "transcripts.originals.%s" % k, art,
                                    srt=(k == "srt"))
        for i, lo in enumerate(tr.get("llm_outputs") or []):
            base = "transcripts.llm_outputs[%d]" % i
            if not _type_ok(lo, (dict,)):
                _err(rec, p, base, "must be object")
                continue
            for k in ("job_type", "model", "llm_output_id", "status"):
                if k not in lo:
                    _err(rec, p, base + "." + k, "missing")
            # Escape valve (docs/CORPUS_DATA_MODEL.md): records with a NEW job
            # type get the literal type + a mapper warning, NOT a validation
            # failure. Only a missing / non-string job_type is a hard error.
            if not _type_ok(lo.get("job_type"), (str,)):
                _err(rec, p, base + ".job_type", "must be a string")
            if not _type_ok(lo.get("llm_output_id"), (int,)):
                _err(rec, p, base + ".llm_output_id", "must be int")
            sc = lo.get("srt_content")
            if lo.get("job_type") == "correct_subtitles" and sc:
                if not srtmod.looks_like_srt(sc):
                    _err(rec, p, base + ".srt_content", "corrected SRT does not parse")
        for i, ao in enumerate(tr.get("asr_outputs") or []):
            if not _type_ok(ao, (dict,)) or "asr_output_id" not in ao:
                _err(rec, p, "transcripts.asr_outputs[%d]" % i, "bad shape")

    prov = rec["provenance"]
    if not _type_ok(prov, (dict,)):
        _err(rec, p, "provenance", "must be object")
    else:
        for k in ("exported_at", "export_version", "sources"):
            if k not in prov:
                _err(rec, p, "provenance.%s" % k, "missing")
        if not _type_ok(prov.get("sources"), (list,)):
            _err(rec, p, "provenance.sources", "must be list")

    q = rec["quality"]
    if not _type_ok(q, (dict,)):
        _err(rec, p, "quality", "must be object")
    else:
        if not _type_ok(q.get("missing"), (list,)):
            _err(rec, p, "quality.missing", "must be list")
        if not _type_ok(q.get("warnings"), (list,)):
            _err(rec, p, "quality.warnings", "must be list")
        if q.get("text_normalized") != "NFC":
            _err(rec, p, "quality.text_normalized", "must be 'NFC'")

    _scan_strings(p, rec)
    return p


def _check_artifact(p, base, art, srt=False):
    if not _type_ok(art.get("exists"), (bool,)):
        _err(None, p, base + ".exists", "must be boolean")
    if art.get("relpath") is not None:
        if not isinstance(art["relpath"], str) or art["relpath"].startswith("/"):
            _err(None, p, base + ".relpath", "must be server-relative")
    if srt and art.get("exists") and art.get("content"):
        seg, dur = srtmod.srt_stats(art["content"])
        if seg is None:
            _err(None, p, base + ".content", "SRT content does not parse")
        else:
            if art.get("segment_count") is not None and art["segment_count"] != seg:
                _err(None, p, base + ".segment_count", "mismatch with content")
            if art.get("duration_sec") is not None and dur is not None \
                    and abs(art["duration_sec"] - dur) > 0.5:
                _err(None, p, base + ".duration_sec", "mismatch with content")
    if art.get("exists") and art.get("content") is None and art.get("sha256") is None:
        _err(None, p, base, "exists but has neither content nor sha256")


def _scan_strings(p, node, path="$"):
    if isinstance(node, str):
        if PRIVATE_PATH_RE.search(node):
            _err(None, p, path, "server-private path leaked: %r" % node[:80])
        for rx in SECRET_PATTERNS:
            if rx.search(node):
                _err(None, p, path, "possible secret leaked: %r" % node[:80])
                break
    elif isinstance(node, dict):
        for k, v in node.items():
            _scan_strings(p, v, path + "." + str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _scan_strings(p, v, "%s[%d]" % (path, i))


def validate_batch(records):
    """Validate a list of records (batch-level id uniqueness).
    Returns (problems_by_record_id, n_ok)."""
    seen = set()
    out = {}
    ok = 0
    for rec in records:
        rid = rec.get("record_id") if isinstance(rec, dict) else None
        probs = validate_record(rec, seen_ids=seen)
        if probs:
            out[rid or "<unknown>"] = probs
        else:
            ok += 1
    return out, ok
