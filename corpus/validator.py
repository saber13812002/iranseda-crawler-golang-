"""Structural record validator (pure stdlib — no jsonschema dependency).

Validates corpus records against the v1 contract WITHOUT the jsonschema
library (53's venv lacks it). Stage 4: accepts BOTH schema_version "1.0"
and "1.1" (spec §8.1 / §11 compatibility). v1.1 records get the additive
linkage checks in :func:`_check_v11` (identity uids, the linkage block,
null-not-empty-string discipline, quarantine no-public-links R4, date
classification consistency). It enforces the same structural rules as
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
import datetime

from . import srt as srtmod
from . import assets as _assets

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

    if rec["schema_version"] not in ("1.0", "1.1"):
        _err(rec, p, "schema_version", "must be '1.0' or '1.1'")

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

    if rec["schema_version"] == "1.1":
        _check_v11(rec, p)

    _scan_strings(p, rec)
    return p


# ---------------------------------------------------------------------------
# v1.1 additive checks (Stage 4 — spec §8.1 / §8.2, D-1, R4)
# ---------------------------------------------------------------------------

LINK_TYPES = ("episode", "day_archive", "time_slot", "program_page")
LINK_STATUSES = ("eligible", "not_eligible", "excluded")
DATE_STATUSES = ("confirmed", "unverified", "impossible", "none")
PROGRAM_UID_RE = re.compile(r"^iranseda:prog:ch[0-9]+:m[0-9]+$")
_URL_RE = re.compile(r"^https?://\S+$")
_ASSET_TYPES = set(_assets.ASSET_TYPES)


def _nonempty_str(v):
    return isinstance(v, str) and v != ""


def _int_ge_0(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _check_v11(rec, p):
    """Additive v1.1 field checks (only called when schema_version=='1.1').

    Null discipline: every NEW string field is null or a non-empty string
    (never ""). Link discipline: status <-> url consistency, cross-link
    rules, and R4 (quarantined records get no public links).
    """
    # -- identity uids (D-1) ------------------------------------------
    suid = rec.get("session_uid")
    if not _nonempty_str(suid):
        _err(rec, p, "session_uid", "must be non-empty string (v1.1)")
    elif not RECORD_ID_RE.match(suid):
        _err(rec, p, "session_uid", "bad pattern: %r" % (suid,))
    elif suid != rec.get("record_id"):
        _err(rec, p, "session_uid", "must equal record_id")

    sstat = rec.get("session_uid_status")
    if sstat not in ("link", "fallback_db"):
        _err(rec, p, "session_uid_status", "bad enum %r" % (sstat,))
    else:
        if sstat != rec["episode_key"].get("source"):
            _err(rec, p, "session_uid_status",
                 "must match episode_key.source")
        if _nonempty_str(suid):
            expect = ("link" if suid.startswith("iranseda:ch")
                      else "fallback_db")
            if sstat != expect:
                _err(rec, p, "session_uid_status",
                     "prefix mismatch: uid %r vs status %r" % (suid, sstat))

    if "program_uid" not in rec:
        _err(rec, p, "program_uid", "missing (v1.1)")
    else:
        puid = rec["program_uid"]
        if puid is not None and not (
                isinstance(puid, str) and PROGRAM_UID_RE.match(puid)):
            _err(rec, p, "program_uid", "bad pattern: %r" % (puid,))

    pstat = rec.get("program_uid_status")
    if pstat not in ("ok", "unresolved", "no_program"):
        _err(rec, p, "program_uid_status", "bad enum %r" % (pstat,))
    elif "program_uid" in rec:
        if pstat == "ok" and rec["program_uid"] is None:
            _err(rec, p, "program_uid_status",
                 "'ok' requires non-null program_uid")
        if pstat != "ok" and rec["program_uid"] is not None:
            _err(rec, p, "program_uid_status",
                 "%r requires null program_uid" % pstat)

    # -- linkage block ---------------------------------------------------
    lg = rec.get("linkage")
    if not _type_ok(lg, (dict,)):
        _err(rec, p, "linkage", "must be object (v1.1)")
        return
    for k in ("linkage_version", "timezone", "links", "air_date_status",
              "validity", "day_of_week", "quarantined", "last_verified_at",
              "asset_summary", "assets_ref"):
        if k not in lg:
            _err(rec, p, "linkage.%s" % k, "missing")
    if lg.get("linkage_version") != "1.1":
        _err(rec, p, "linkage.linkage_version", "must be '1.1'")
    if lg.get("timezone") != "Asia/Tehran":
        _err(rec, p, "linkage.timezone", "must be 'Asia/Tehran'")

    dstat = lg.get("air_date_status")
    if dstat not in DATE_STATUSES:
        _err(rec, p, "linkage.air_date_status", "bad enum %r" % (dstat,))

    val = lg.get("validity")
    if not _type_ok(val, (dict,)):
        _err(rec, p, "linkage.validity", "must be object")
    else:
        if val.get("status") not in DATE_STATUSES:
            _err(rec, p, "linkage.validity.status", "bad enum")
        elif dstat in DATE_STATUSES and val.get("status") != dstat:
            _err(rec, p, "linkage.validity.status",
                 "must equal air_date_status")
        reasons = val.get("reasons")
        if not _type_ok(reasons, (list,)) or not all(
                isinstance(r, str) for r in reasons):
            _err(rec, p, "linkage.validity.reasons",
                 "must be list of strings")

    dow = lg.get("day_of_week")
    if (dow is not None
            and not (isinstance(dow, int) and not isinstance(dow, bool)
                     and 1 <= dow <= 7)):
        _err(rec, p, "linkage.day_of_week", "must be int 1..7 or null")

    quar = lg.get("quarantined")
    if not _type_ok(quar, (bool,)):
        _err(rec, p, "linkage.quarantined", "must be boolean")

    if "last_verified_at" in lg and lg["last_verified_at"] is not None \
            and not _nonempty_str(lg["last_verified_at"]):
        _err(rec, p, "linkage.last_verified_at",
             "must be non-empty string or null")

    if "assets_ref" in lg and not _nonempty_str(lg.get("assets_ref")):
        _err(rec, p, "linkage.assets_ref", "must be non-empty string")

    # -- links ------------------------------------------------------------
    links = lg.get("links")
    seen_types = set()
    status_by_type = {}
    if not _type_ok(links, (list,)) or not links:
        _err(rec, p, "linkage.links", "must be non-empty list")
        links = []
    for i, lk in enumerate(links or []):
        base = "linkage.links[%d]" % i
        if not _type_ok(lk, (dict,)):
            _err(rec, p, base, "must be object")
            continue
        lt = lk.get("type")
        if lt not in LINK_TYPES:
            _err(rec, p, base + ".type", "bad enum %r" % (lt,))
        elif lt in seen_types:
            _err(rec, p, base + ".type", "duplicate link type %s" % lt)
        seen_types.add(lt)
        url = lk.get("url", "MISSING")
        if "url" not in lk:
            _err(rec, p, base + ".url", "missing")
        elif url is not None and not (isinstance(url, str)
                                      and _URL_RE.match(url)):
            _err(rec, p, base + ".url",
                 "must be http(s) URL or null: %r" % (url,))
        if "url_normalized" not in lk:
            _err(rec, p, base + ".url_normalized", "missing")
        elif lk["url_normalized"] is not None and not _nonempty_str(
                lk["url_normalized"]):
            _err(rec, p, base + ".url_normalized",
                 "must be non-empty string or null")
        st = lk.get("status")
        if st not in LINK_STATUSES:
            _err(rec, p, base + ".status", "bad enum %r" % (st,))
        if "reason" not in lk:
            _err(rec, p, base + ".reason", "missing")
        elif lk["reason"] is not None and not _nonempty_str(lk["reason"]):
            _err(rec, p, base + ".reason",
                 "must be non-empty string or null")
        # status <-> url discipline (null discipline, spec §7.2)
        if st == "eligible" and url is None:
            _err(rec, p, base, "'eligible' requires a non-null url")
        if st in ("not_eligible", "excluded") and url is not None:
            _err(rec, p, base, "%s requires null url" % st)
        if st == "excluded" and quar is not True:
            _err(rec, p, base, "'excluded' requires quarantined=true")
        if st == "eligible" and quar is True:
            _err(rec, p, base, "'eligible' not allowed when quarantined")
        status_by_type[lt] = st

    # cross-link rules (date classification consistency)
    if dstat in ("impossible", "none"):
        for i, lk in enumerate(links or []):
            if _type_ok(lk, (dict,)) \
                    and lk.get("type") in ("day_archive", "time_slot") \
                    and lk.get("url") is not None:
                _err(rec, p, "linkage.links[%d]" % i,
                     "%s url must be null when air_date_status=%s"
                     % (lk.get("type"), dstat))
    if status_by_type.get("time_slot") == "eligible" \
            and status_by_type.get("day_archive") != "eligible":
        _err(rec, p, "linkage.links",
             "time_slot eligible requires day_archive eligible")
    if quar is True:
        for i, lk in enumerate(links or []):
            if _type_ok(lk, (dict,)) and (
                    lk.get("url") is not None
                    or lk.get("url_normalized") is not None):
                _err(rec, p, "linkage.links[%d]" % i,
                     "quarantined record must have null public links (R4)")

    # -- asset_summary ------------------------------------------------------
    s = lg.get("asset_summary")
    if not _type_ok(s, (dict,)):
        _err(rec, p, "linkage.asset_summary", "must be object")
    else:
        total = s.get("total")
        if not _int_ge_0(total):
            _err(rec, p, "linkage.asset_summary.total", "must be int >= 0")
        by_type = s.get("by_type")
        if not _type_ok(by_type, (dict,)):
            _err(rec, p, "linkage.asset_summary.by_type", "must be object")
        else:
            for k, v in by_type.items():
                if not _int_ge_0(v):
                    _err(rec, p, "linkage.asset_summary.by_type.%s" % k,
                         "must be int >= 0")
                if k not in _ASSET_TYPES:
                    _err(rec, p, "linkage.asset_summary.by_type.%s" % k,
                         "unknown asset type")
        for k in ("on_disk", "in_git_tree"):
            if k not in s:
                _err(rec, p, "linkage.asset_summary.%s" % k, "missing")
            elif s[k] is not None and not _int_ge_0(s[k]):
                _err(rec, p, "linkage.asset_summary.%s" % k,
                     "must be int >= 0 or null")
        parts = {}
        for k in ("published", "not_published", "missing", "unknown",
                  "excluded"):
            if k not in s:
                _err(rec, p, "linkage.asset_summary.%s" % k, "missing")
            elif not _int_ge_0(s[k]):
                _err(rec, p, "linkage.asset_summary.%s" % k,
                     "must be int >= 0")
            else:
                parts[k] = s[k]
        if len(parts) == 5 and _int_ge_0(total) \
                and sum(parts.values()) != total:
            _err(rec, p, "linkage.asset_summary",
                 "state counts must sum to total")
        if quar is True:
            if parts.get("published", 0) != 0 \
                    or parts.get("excluded", -1) != (total or 0):
                _err(rec, p, "linkage.asset_summary",
                     "quarantined: published=0 and excluded==total (R4)")

    # -- broadcast 1.1 additions ------------------------------------------
    b = rec.get("broadcast")
    if _type_ok(b, (dict,)):
        if b.get("timezone") != "Asia/Tehran":
            _err(rec, p, "broadcast.timezone",
                 "must be 'Asia/Tehran' (v1.1)")
        bv = b.get("validity")
        if not _type_ok(bv, (dict,)):
            _err(rec, p, "broadcast.validity", "must be object (v1.1)")
        else:
            if bv.get("status") not in DATE_STATUSES:
                _err(rec, p, "broadcast.validity.status", "bad enum")
            elif dstat in DATE_STATUSES and bv.get("status") != dstat:
                _err(rec, p, "broadcast.validity.status",
                     "must equal linkage.air_date_status")
            if not _type_ok(bv.get("reasons"), (list,)):
                _err(rec, p, "broadcast.validity.reasons", "must be list")
        bdw = b.get("day_of_week")
        if (bdw is not None
                and not (isinstance(bdw, int)
                         and not isinstance(bdw, bool)
                         and 1 <= bdw <= 7)):
            _err(rec, p, "broadcast.day_of_week", "must be int 1..7 or null")
        g = b.get("gregorian")
        if _type_ok(g, (dict,)) and DATE_RE.match(g.get("date") or ""):
            try:
                y, mo, d = (int(x) for x in g["date"].split("-"))
                expect_dow = datetime.date(y, mo, d).isoweekday()
            except (ValueError, TypeError):
                expect_dow = None
            if expect_dow is not None and bdw is not None \
                    and bdw != expect_dow:
                _err(rec, p, "broadcast.day_of_week",
                     "does not match gregorian date (expect %d)" % expect_dow)


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
