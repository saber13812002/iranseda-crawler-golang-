"""Mapper: DB rows + disk index -> corpus record dict (v1 contract).

Implements docs/CORPUS_FIELD_MAPPING.md field by field. Every gap is
explicit (quality.missing / quality.warnings) — never silently dropped.
"""

import json
import os
import hashlib
import datetime

from . import normalizer
from . import srt as srtmod
from . import jalali
from . import database as _db
from . import linkage as _linkage
from . import assets as _assets


def _iso(dt):
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        s = dt.isoformat()
        # normalize to a plain 'YYYY-MM-DD HH:MM:SS[+HH:MM]' for readability
        return s.replace("T", " ")[:26] if "T" in s else s
    return str(dt)


def _boolish(v):
    if v is None:
        return None
    return bool(int(v))


def _time_of_day(t):
    """Normalize a MySQL TIME value to 'HH:MM:SS'.

    pymysql decodes a TIME column as datetime.timedelta (the live
    radio_programs.time column is TIME; older repo dumps say varchar).
    Tolerate timedelta / datetime.time / datetime / str without crashing.
    """
    if t is None:
        return None
    if isinstance(t, datetime.timedelta):
        total = int(t.total_seconds())
        if total < 0:
            total += 24 * 3600  # MySQL TIME can be negative; wrap to 0..86399
        if 0 <= total < 24 * 3600:
            h, rem = divmod(total, 3600)
            m, s = divmod(rem, 60)
            return "%02d:%02d:%02d" % (h, m, s)
        return str(t)
    if hasattr(t, "strftime"):
        return t.strftime("%H:%M:%S")
    return str(t)


def _time_to_seconds(t):
    """Normalize a MySQL TIME value to integer seconds (or None).

    radio_programs.crop_offset is a TIME column in the live DB (pymysql
    decodes it as datetime.timedelta; the repo SQL dump says varchar —
    stale). The v1 contract type for program.crop.offset_sec is
    ["integer","null"], so seconds are the canonical representation.
    The raw timedelta crashed json.dumps on 53 at record #418
    (probe-18, 2026-11-04). Tolerate time/datetime/str defensively.
    """
    if t is None:
        return None
    if isinstance(t, datetime.timedelta):
        return int(t.total_seconds())
    if hasattr(t, "hour"):
        return t.hour * 3600 + t.minute * 60 + t.second
    s = str(t).strip()
    try:
        parts = [int(p) for p in s.split(":")]
        parts = [0] * (3 - len(parts)) + parts
        h, m, sec = parts
        return h * 3600 + m * 60 + sec
    except (ValueError, AttributeError):
        return None


def _sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _read_text(path):
    try:
        with open(path, "rb") as f:
            raw = f.read()
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")
    except OSError:
        return None


def _disk_file(disk, relpath, inline):
    """Resolve a server-relative path -> (abspath or None)."""
    if not relpath:
        return None
    if disk is not None:
        p = disk.find(relpath)
        if p:
            return p
    return None


def _artifact_for_path(disk, relpath, abspath, inline, content_is_srt=False,
                       db_filename=None, missing_reason=None):
    """Build an $defs/artifact object for a resolved (or unresolved) path."""
    art = {
        "exists": abspath is not None,
        "db_filename": db_filename,
        "relpath": relpath if abspath is not None else None,
        "content": None,
        "sha256": None,
        "char_count": None,
        "segment_count": None,
        "duration_sec": None,
        "missing_reason": missing_reason,
    }
    if abspath is not None:
        if relpath:
            art["relpath"] = relpath
        if inline:
            content = _read_text(abspath)
            if content is not None:
                content = normalizer.nfc(content)
                art["content"] = content
                art["sha256"] = _sha256_text(content)
                art["char_count"] = len(content)
        else:
            art["sha256"] = _sha256_file(abspath)
            try:
                art["char_count"] = os.path.getsize(abspath)
            except OSError:
                pass
        if content_is_srt:
            if art.get("content") is not None:
                seg, dur = srtmod.srt_stats(art["content"])
            else:
                c = _read_text(abspath)
                seg, dur = srtmod.srt_stats(normalizer.nfc(c) if c else c)
            art["segment_count"] = seg
            art["duration_sec"] = dur
    return art


def _resolve_original_srt(disk, session, warnings):
    """Find the original SRT. Returns (relpath, abspath, used_name).

    Order: top-level downloads/ FIRST, then downloads/cleaned/.

    Ground truth (53, probe-14, 2026-11-04): of 4695 sessions with
    srt_filename, 4483 have the SRT only at downloads/<srt_filename> and
    212 have it in BOTH places — in those 212 the cleaned copy is a legacy
    plain-text artifact (0/212 parse as SRT) while the top-level copy is
    the real whisper SRT (212/212 parse). Zero sessions have a
    cleaned-only copy. So top-level-first is always correct; among
    existing candidates we additionally prefer one that parses as SRT.
    """
    from . import jalali as _j
    candidates = []
    srt_name = (session.get("srt_filename") or "").strip()
    if srt_name:
        candidates.append(("downloads/%s" % srt_name, srt_name))
        candidates.append(("downloads/cleaned/%s" % srt_name, srt_name))
    audio_name = (session.get("filename") or "").strip()
    stem = _j.stem_of(audio_name)
    if stem and not srt_name:
        candidates.append(("downloads/%s.srt" % stem, stem + ".srt"))
        candidates.append(("downloads/cleaned/%s.srt" % stem, stem + ".srt"))
    existing = []
    for relpath, used in candidates:
        abspath = _disk_file(disk, relpath, True) if disk is not None else None
        if abspath is not None:
            existing.append((relpath, abspath, used))
    if not existing:
        if srt_name:
            return "downloads/%s" % srt_name, None, srt_name
        return None, None, None
    # Prefer a candidate that actually parses as SRT (defends against a
    # stray text artifact at a top-level path).
    for relpath, abspath, used in existing:
        content = _read_text(abspath)
        if content is not None and srtmod.looks_like_srt(content):
            return relpath, abspath, used
    return existing[0]


def _merge_program(prog_rows):
    """Merge legacy + current program rows sharing (ch,m) (mapping §2).

    Returns (merged_dict, warnings, ids_all).
    """
    warnings = []
    non_legacy = [r for r in prog_rows if not r.get("is_legacy")]
    legacy = [r for r in prog_rows if r.get("is_legacy")]
    primary = (non_legacy or prog_rows)[0]
    if legacy and non_legacy:
        warnings.append("legacy_program_duplicate_merged")
    ids_all = [r["id"] for r in prog_rows]

    name_raw = primary.get("name")
    name = normalizer.normalize_text(name_raw)
    url = primary.get("url") or ""
    ch = _db.Database.parse_ch(url)
    m = _db.Database.parse_m(url)

    radio = (primary.get("radio") or "").strip() or None
    if radio:
        radio = normalizer.nfc(radio)
    description = normalizer.normalize_text(primary.get("description"))

    start_time = _time_of_day(primary.get("time"))
    td_raw = primary.get("time_description")
    td = normalizer.normalize_text(td_raw)
    if td_raw is not None and normalizer.has_control_chars(td_raw):
        warnings.append("time_description_malformed")
    if start_time:
        sched_source = "programs.time"
    elif td is not None and td != "":
        sched_source = "programs.time_description"
    else:
        sched_source = "none"

    crop = None
    if primary.get("crop_offset") is not None or primary.get("crop_enabled") is not None:
        crop = {
            "offset_sec": _time_to_seconds(primary.get("crop_offset")),
            "enabled": _boolish(primary.get("crop_enabled")),
            "auto": _boolish(primary.get("crop_auto")),
        }

    merged = {
        "name": name or "",
        "name_raw": name_raw,
        "url": url,
        "ch": ch,
        "m": m,
        "radio": radio,
        "description": description,
        "schedule": {
            "start_time": start_time,
            "description_raw": td_raw,
            "description_normalized": td,
            "source": sched_source,
        },
        "crop": crop,
    }
    return merged, warnings, ids_all


# ---------------------------------------------------------------------------
# v1.1 linkage fields (Stage 4 — CORPUS_LINKAGE_SPEC.md §8.1 / §8.2)
# ---------------------------------------------------------------------------

LINKAGE_VERSION = "1.1"
ASSET_MANIFEST_REF = "asset_manifest.jsonl"


def program_uid_for(program):
    """Canonical program identity 'iranseda:prog:ch<ch>:m<m>' (D-1) or
    None when the program row carries no ch/m (absent -> null, never
    fabricated)."""
    ch = (program or {}).get("ch")
    m = (program or {}).get("m")
    if ch is None or m is None:
        return None
    return "iranseda:prog:ch%d:m%s" % (ch, m)


def _day_of_week(gregorian_date):
    """'YYYY-MM-DD' -> ISO weekday int 1=Mon..7=Sun, or None."""
    if not gregorian_date:
        return None
    try:
        y, mo, d = (int(x) for x in str(gregorian_date).split("-"))
        return datetime.date(y, mo, d).isoweekday()
    except (ValueError, TypeError):
        return None


def _session_asset_candidates(session, llm_rows):
    """Per-session asset candidates [(asset_type, relpath), ...].

    Mirrors corpus.assets.build_registry sources (audio, raw_srt, LLM
    artifacts via JOB_TO_ASSET, summary_en pattern) without the GitHub
    branch requirement, so the in-record asset summary works even when
    the asset-manifest identity (GITHUB_BRANCH) is unavailable. Dedup on
    (asset_type, relpath); the latest llm_output id wins.
    """
    fname = (session.get("filename") or "").strip()
    srtf = (session.get("srt_filename") or "").strip()
    cands = {}

    def add(asset_type, relpath, sort_id):
        relpath = _assets._norm_relpath(relpath)
        key = (asset_type, relpath)
        prev = cands.get(key)
        if prev is None or sort_id > prev[2]:
            cands[key] = (asset_type, relpath, sort_id)

    if fname:
        add("audio", "downloads/" + os.path.basename(fname), 0)
    if srtf:
        add("raw_srt", "downloads/" + os.path.basename(srtf), 0)
    for r in sorted(llm_rows or [], key=lambda r: int(r.get("id") or 0)):
        rel = (r.get("file_relpath") or "").strip()
        if rel:
            add(_assets.JOB_TO_ASSET.get(r.get("job_type"), "other_llm"),
                rel, int(r.get("id") or 0))
    if fname:
        parse = _assets.parse_asset_filename(fname)
        if parse and parse["stem_family"] == "canonical":
            add("summary_en",
                "downloads/cleaned/%s.summary.en.txt" % parse["stem"], -1)
    return [(a, r) for (a, r, _s) in cands.values()]


def _asset_summary_rows(session, llm_rows, disk, git_paths):
    """Cheap per-asset status.

    Tiering decision (Stage 4): the corpus pass records disk presence
    + single ``git ls-tree`` set membership only — NO HTTP and NO
    per-file git log. The full C1-C14 five-way verification stays in
    corpus/asset_manifest.jsonl (Stage 3 tooling).
    """
    rows = []
    for asset_type, relpath in _session_asset_candidates(session, llm_rows):
        on_disk = None if disk is None else (disk.find(relpath) is not None)
        in_git = None if git_paths is None else (relpath in git_paths)
        if on_disk is None or in_git is None:
            state = "unknown"
        elif not on_disk:
            state = "missing"
        elif not in_git:
            state = "not_published"
        else:
            state = "published"
        rows.append({
            "asset_type": asset_type,
            "relpath": relpath,
            "on_disk": on_disk,
            "in_git_tree": in_git,
            "state": state,
        })
    return rows


def build_linkage_block(ch, e, program, validity, session, llm_rows, disk,
                        cfg, linkage_ctx):
    """The v1.1 top-level ``linkage`` object (spec §8.1).

    ``validity`` is the corpus.linkage.classify_date(session) result.
    ``linkage_ctx``: optional {"git_paths": set|None} — the single
    ``git ls-tree -r <branch> --name-only`` relpath set (see
    corpus.rag_linkage).

    Link eligibility (spec §6 + Stage 2 evidence):
      * episode      — always, when ch and e are present.
      * day_archive  — only when the date is unverified/confirmed AND a
                       gregorian date is resolvable (NOT for impossible;
                       §4.2 keeps the parsed date for audit, links off).
      * time_slot    — day_archive eligible + start time present.
      * program_page — the stored radio_programs.url verbatim plus the
                       normalized form (OQ-3).
    """
    site_base = cfg.site_base
    date_status = validity["status"]
    gdate = (validity.get("gregorian") or {}).get("date")
    jtime = (validity.get("jalali") or {}).get("time")

    links = []
    if ch is not None and e is not None:
        links.append({
            "type": _linkage.LINK_EPISODE,
            "url": _linkage.build_episode_url(ch, e, site_base),
            "url_normalized": None,
            "status": "eligible",
            "reason": None,
        })
    else:
        links.append({
            "type": _linkage.LINK_EPISODE,
            "url": None,
            "url_normalized": None,
            "status": "not_eligible",
            "reason": "missing_episode_key",
        })

    day_ok = (ch is not None and gdate is not None
              and date_status in (_linkage.DATE_STATUS_UNVERIFIED,
                                  _linkage.DATE_STATUS_CONFIRMED))
    if day_ok:
        links.append({
            "type": _linkage.LINK_DAY_ARCHIVE,
            "url": _linkage.build_day_archive_url(ch, gdate, site_base),
            "url_normalized": None,
            "status": "eligible",
            "reason": None,
        })
    else:
        if ch is None:
            reason = "missing_channel"
        elif date_status == _linkage.DATE_STATUS_IMPOSSIBLE:
            reason = "impossible_date"
        elif date_status == _linkage.DATE_STATUS_NONE:
            reason = "no_date"
        else:
            reason = "date_unresolved"
        links.append({
            "type": _linkage.LINK_DAY_ARCHIVE,
            "url": None,
            "url_normalized": None,
            "status": "not_eligible",
            "reason": reason,
        })

    if day_ok and jtime:
        links.append({
            "type": _linkage.LINK_TIME_SLOT,
            "url": _linkage.build_time_slot_url(ch, jtime, gdate, site_base),
            "url_normalized": None,
            "status": "eligible",
            "reason": None,
        })
    else:
        links.append({
            "type": _linkage.LINK_TIME_SLOT,
            "url": None,
            "url_normalized": None,
            "status": "not_eligible",
            "reason": "no_start_time" if day_ok else links[1]["reason"],
        })

    prog = _linkage.build_program_page_url(program, site_base)
    if prog["raw"]:
        links.append({
            "type": _linkage.LINK_PROGRAM,
            "url": prog["raw"],
            "url_normalized": prog["normalized"],
            "status": "eligible",
            "reason": None,
        })
    else:
        links.append({
            "type": _linkage.LINK_PROGRAM,
            "url": None,
            "url_normalized": None,
            "status": "not_eligible",
            "reason": "no_program_url",
        })

    git_paths = (linkage_ctx or {}).get("git_paths")
    rows = _asset_summary_rows(session, llm_rows, disk, git_paths)
    by_type = {}
    counts = {"published": 0, "not_published": 0, "missing": 0, "unknown": 0}
    for r in rows:
        by_type[r["asset_type"]] = by_type.get(r["asset_type"], 0) + 1
        counts[r["state"]] += 1
    asset_summary = {
        "total": len(rows),
        "by_type": dict(sorted(by_type.items())),
        "on_disk": (None if disk is None
                    else sum(1 for r in rows if r["on_disk"])),
        "in_git_tree": (None if git_paths is None
                        else sum(1 for r in rows if r["in_git_tree"])),
        "published": counts["published"],
        "not_published": counts["not_published"],
        "missing": counts["missing"],
        "unknown": counts["unknown"],
        "excluded": 0,
    }

    return {
        "linkage_version": LINKAGE_VERSION,
        "timezone": _linkage.TIMEZONE,
        "links": links,
        "air_date_status": date_status,
        "validity": {
            "status": date_status,
            "reasons": list(validity["reasons"] or []),
        },
        "day_of_week": _day_of_week(gdate),
        "quarantined": False,
        "last_verified_at": None,
        "asset_summary": asset_summary,
        "assets_ref": ASSET_MANIFEST_REF,
    }


def apply_quarantine_linkage(rec):
    """R4 (spec §10): quarantined records receive NO public links.

    Applies to the NEW v1.1 linkage surface only; pre-existing v1.0
    fields (audio.url, source_metadata.*) are left untouched for
    byte-invariance (documented interpretation, Stage 4 report).
    Identity uids remain (the record still identifies the session).
    """
    if rec.get("schema_version") != "1.1":
        return
    lg = rec.get("linkage")
    if not isinstance(lg, dict):
        return
    lg["quarantined"] = True
    for lk in lg.get("links") or []:
        lk["url"] = None
        lk["url_normalized"] = None
        lk["status"] = "excluded"
        lk["reason"] = "quarantined_no_public_links"
    s = lg.get("asset_summary")
    if isinstance(s, dict):
        s["published"] = 0
        s["not_published"] = 0
        s["missing"] = 0
        s["unknown"] = 0
        s["excluded"] = s.get("total") or 0
    quality = rec.get("quality")
    if isinstance(quality, dict):
        warnings = set(quality.get("warnings") or [])
        warnings.add("quarantined_no_public_links")
        quality["warnings"] = sorted(warnings)


def build_record(session, prog_by_id, prog_by_chm, llm_rows, asr_rows, crop_row,
                 disk, cfg, run_id, exported_at,
                 schema_version="1.1", linkage_ctx=None):
    """One corpus record (dict) for one session row.

    Stage 4: ``schema_version="1.1"`` (default) adds the additive
    linkage fields (spec §8.1): session_uid, session_uid_status,
    program_uid, program_uid_status, broadcast.{timezone, validity,
    day_of_week} and the top-level linkage block. ``schema_version="1.0"``
    reproduces the pre-Stage-4 record byte-for-byte (invariance gate).
    ``linkage_ctx``: optional {"git_paths": set|None} — the single
    ``git ls-tree -r`` relpath set for the asset branch (tiering:
    no per-asset HTTP / git-log in the corpus pass).
    """
    warnings = []
    missing = []

    sid = int(session["id"])
    pid = session.get("program_id")
    link = session.get("link") or ""

    # ---- identity -------------------------------------------------
    ch = _db.Database.parse_ch(link)
    e = _db.Database.parse_e(link)
    prog = prog_by_id.get(pid) if pid is not None else None
    m = None
    if prog is not None:
        m = _db.Database.parse_m(prog.get("url"))
    if ch is not None and e is not None:
        record_id = "iranseda:ch%d:e%s" % (ch, e)
        key_source = "link"
    else:
        record_id = "iranseda:db%s:s%d" % (
            pid if pid is not None else "x", sid)
        key_source = "fallback_db"
        if ch is None or e is None:
            warnings.append("episode_key_fallback_db")

    program_ids_all = []
    if prog is not None:
        key = (_db.Database.parse_ch(prog.get("url")), m)
        if key[0] is not None and key[1] is not None:
            program_ids_all = sorted(prog_by_chm.get(key, [prog["id"]]))
        else:
            program_ids_all = [prog["id"]]
    elif pid is not None:
        program_ids_all = [pid]

    # ---- program --------------------------------------------------
    prog_rows = []
    if program_ids_all:
        prog_rows = [prog_by_id[i] for i in program_ids_all if i in prog_by_id]
    elif prog is not None:
        prog_rows = [prog]
    if prog_rows:
        program, pwarn, ids_all = _merge_program(prog_rows)
        warnings.extend(pwarn)
        program_ids_all = ids_all or program_ids_all
    else:
        program = {
            "name": "",
            "name_raw": None,
            "url": "",
            "ch": None,
            "m": None,
            "radio": None,
            "description": None,
            "schedule": None,
            "crop": None,
        }
        missing.append("program")
        warnings.append("program_row_missing")
    program_present = bool(prog_rows)
    if not program.get("name"):
        missing.append("program.name")

    # ---- broadcast ------------------------------------------------
    filename = (session.get("filename") or "").strip()
    stem = jalali.stem_of(filename)
    broadcast = None
    if not filename:
        missing.append("broadcast.date")
    else:
        parsed = jalali.parse_broadcast(stem)
        if parsed is None:
            warnings.append("filename_pattern_mismatch")
            missing.append("broadcast.date")
        else:
            broadcast = dict(parsed)
            broadcast["filename_stem"] = stem
    if broadcast is not None and "filename_stem" not in broadcast:
        broadcast["filename_stem"] = stem

    # ---- audio ----------------------------------------------------
    audio_url = _resolve_url(link, cfg.site_base)
    audio = {
        "url": audio_url,
        "link_raw": link or None,
        "filename": filename or None,
        "local_exists": False,
    }
    if disk is not None and filename:
        for cand in ("downloads/" + filename,):
            if disk.find(cand) is not None:
                audio["local_exists"] = True
                break

    # ---- transcripts: originals ------------------------------------
    srt_rel, srt_abs, srt_used = _resolve_original_srt(disk, session, warnings)
    srt_inline = cfg.inline_originals
    srt_art = _artifact_for_path(
        disk, srt_rel, srt_abs, srt_inline,
        content_is_srt=True,
        db_filename=(session.get("srt_filename") or "").strip() or None,
        missing_reason=None if srt_abs else (
            "srt_not_on_disk" if srt_rel else "no_srt_filename"),
    )
    if not srt_art["exists"]:
        missing.append("transcripts.originals.srt")
    elif srt_art["content"] is None and not srt_inline:
        missing.append("transcripts.originals.srt.content")

    # txt: same dir/stem as the resolved SRT (or srt stem from DB name)
    txt_rel = None
    txt_abs = None
    if srt_abs:
        base = os.path.splitext(os.path.basename(srt_abs))[0]
        # derive from the (forward-slash) relpath, not the absolute path —
        # the "/cleaned/" substring check breaks on Windows backslash paths
        txt_rel = os.path.dirname(srt_rel) + "/" + base + ".txt"
        txt_abs = _disk_file(disk, txt_rel, True) if disk is not None else None
    else:
        sdb = (session.get("srt_filename") or "").strip()
        if sdb:
            base = os.path.splitext(os.path.basename(sdb))[0]
            for rel in ("downloads/cleaned/%s.txt" % base, "downloads/%s.txt" % base):
                txt_abs = _disk_file(disk, rel, True) if disk is not None else None
                if txt_abs:
                    txt_rel = rel
                    break
    txt_art = _artifact_for_path(
        disk, txt_rel, txt_abs, srt_inline,
        content_is_srt=False,
        missing_reason=None if txt_abs else (
            "derived_txt_not_on_disk" if srt_abs else "no_srt"),
    )
    if not txt_art["exists"]:
        missing.append("transcripts.originals.txt")
    elif txt_art["content"] is None and not srt_inline:
        missing.append("transcripts.originals.txt.content")

    # ---- transcripts: llm outputs ----------------------------------
    llm_entries = []
    llm_ids = []
    for r in sorted(llm_rows or [], key=lambda x: x["id"]):
        jt = r.get("job_type")
        if jt not in ("correct_subtitles", "correct_text", "summary",
                      "full_text", "qa"):
            warnings.append("unknown_job_type:%s" % jt)
        content = r.get("content")
        content_en = r.get("content_en")
        srt_content = r.get("srt_content")
        rel = r.get("file_relpath")
        abspath = _disk_file(disk, rel, True) if (disk is not None and rel) else None
        disk_exists = abspath is not None
        inline = cfg.inline_llm
        ent = {
            "llm_output_id": int(r["id"]),
            "job_type": jt,
            "model": r.get("model"),
            "prompt_id": r.get("prompt_id"),
            "status": r.get("status"),
            "content": None,
            "content_en": None,
            "srt_content": None,
            "file_relpath": rel,
            "disk_exists": disk_exists,
            "input_tokens": r.get("input_tokens"),
            "output_tokens": r.get("output_tokens"),
            "started_at": _iso(r.get("started_at")),
            "finished_at": _iso(r.get("finished_at")),
        }
        if inline:
            if content:
                c = normalizer.normalize_text(content)
                ent["content"] = c
            if content_en:
                ent["content_en"] = normalizer.normalize_text(content_en)
            if srt_content:
                sc = normalizer.nfc(srt_content)
                ent["srt_content"] = sc
                if not srtmod.looks_like_srt(sc):
                    warnings.append("llm_srt_content_not_parseable")
        if not disk_exists and rel:
            missing.append("llm_output.%s.disk:%s" % (jt, rel))
        llm_entries.append(ent)
        llm_ids.append(int(r["id"]))

    # ---- transcripts: asr outputs ----------------------------------
    asr_entries = []
    asr_ids = []
    for r in sorted(asr_rows or [], key=lambda x: x["id"]):
        asr_entries.append({
            "asr_output_id": int(r["id"]),
            "provider": r.get("provider"),
            "model_name": r.get("model_name"),
            "model_version": r.get("model_version"),
            "audio_sha256": r.get("audio_sha256"),
            "processing_status": r.get("processing_status"),
            "error_code": r.get("error_code"),
        })
        asr_ids.append(int(r["id"]))

    # ---- crop -------------------------------------------------------
    crop = None
    if crop_row is not None:
        evidence = crop_row.get("evidence")
        ev = None
        if evidence:
            try:
                ev = json.loads(evidence)
            except (ValueError, TypeError):
                warnings.append("crop_evidence_invalid_json")
        crop = {
            "start_sec": crop_row.get("start_sec"),
            "end_sec": crop_row.get("end_sec"),
            "confidence": crop_row.get("confidence"),
            "status": crop_row.get("status"),
            "evidence": ev,
        }

    # ---- source metadata -------------------------------------------
    program_url = program.get("url") or ""
    source_metadata = {
        "episode_url": audio_url,
        "program_url": program_url,
        "site_base": cfg.site_base,
    }

    # ---- pipeline state ---------------------------------------------
    pipeline_state = {
        "status": session.get("status"),
        "is_downloaded": _boolish(session.get("is_downloaded")),
        "attempts": session.get("attempts"),
        # Sanitize last_error: production values embed ffmpeg invocations
        # with absolute server paths (probe19: 53 quarantined records).
        "last_error": normalizer.sanitize_private_paths(
            normalizer.normalize_text(session.get("last_error"))),
    }

    # ---- provenance ---------------------------------------------------
    sources = [
        "radio_program_sessions#%d" % sid,
    ]
    if pid is not None:
        sources.append("radio_programs#%d" % pid)
    for i in llm_ids:
        sources.append("llm_output#%d" % i)
    if crop_row is not None:
        sources.append("crop_detection#%d" % int(crop_row["id"]))
    for i in asr_ids:
        sources.append("asr_output#%d" % i)
    if srt_abs:
        sources.append("disk:%s" % srt_art["relpath"])
    if txt_abs:
        sources.append("disk:%s" % txt_art["relpath"])

    provenance = {
        "exported_at": exported_at,
        "export_version": run_id,
        "sources": sources,
        "session_created_at": _iso(session.get("created_at")),
        "session_updated_at": _iso(session.get("updated_at")),
    }

    # ---- quality -------------------------------------------------------
    quality = {
        "missing": sorted(set(missing)),
        "warnings": sorted(set(warnings)),
        "text_normalized": "NFC",
    }

    rec = {
        "schema_version": schema_version,
        "record_id": record_id,
        "episode_key": {
            "ch": ch,
            "e": e,
            "m": m,
            "source": key_source,
        },
        "database_refs": {
            "session_id": sid,
            "program_id": pid,
            "program_ids_all": program_ids_all,
            "tables": {
                "radio_program_sessions": sid,
                "radio_programs": program_ids_all or None,
                "llm_output": llm_ids,
                "crop_detection": int(crop_row["id"]) if crop_row is not None else None,
                "asr_output": asr_ids,
            },
        },
        "program": program,
        "broadcast": broadcast,
        "audio": audio,
        "speakers": {
            "items": [],
            "missing_reason": "no verified source table in database (stage-1 finding #9)",
        },
        "transcripts": {
            "originals": {"srt": srt_art, "txt": txt_art},
            "llm_outputs": llm_entries,
            "asr_outputs": asr_entries,
            "whisper_provenance": {
                "provider": "whisper (local pipeline, output not registered in asr_output)",
                "details_available": False,
            },
        },
        "crop": crop,
        "source_metadata": source_metadata,
        "pipeline_state": pipeline_state,
        "provenance": provenance,
        "quality": quality,
    }

    if schema_version == "1.1":
        # ---- Stage 4 v1.1 additive fields (spec §8.1, D-1) ----------
        # Additive only: projecting these keys out of a v1.1 record
        # yields the byte-identical v1.0 record (invariance proof).
        validity = _linkage.classify_date(session)
        rec["session_uid"] = record_id
        rec["session_uid_status"] = key_source
        rec["program_uid"] = program_uid_for(program)
        rec["program_uid_status"] = (
            "no_program" if not program_present
            else ("ok" if rec["program_uid"] is not None else "unresolved"))
        if broadcast is not None:
            broadcast["timezone"] = _linkage.TIMEZONE
            broadcast["validity"] = {
                "status": validity["status"],
                "reasons": list(validity["reasons"] or []),
            }
            broadcast["day_of_week"] = _day_of_week(
                (validity.get("gregorian") or {}).get("date"))
        rec["linkage"] = build_linkage_block(
            ch, e, program, validity, session, llm_rows, disk, cfg,
            linkage_ctx)
    return rec


def _resolve_url(link, site_base):
    """session.link (relative ../epgarchivePart/?...) -> absolute URL."""
    link = (link or "").strip()
    if not link:
        return site_base
    if link.startswith("http://") or link.startswith("https://"):
        return link
    if link.startswith("/"):
        return site_base + link.lstrip("/")
    # relative, e.g. '../epgarchivePart/?VALID=TRUE&ch=14&e=...'
    # the site base already ends with '/'; '../' means up to the site root
    core = link
    while core.startswith("../"):
        core = core[3:]
    return site_base + core


def record_fingerprint(record):
    """Deterministic content hash (excludes volatile provenance bits)."""
    import copy
    r = copy.deepcopy(record)
    r.pop("provenance", None)
    blob = json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
