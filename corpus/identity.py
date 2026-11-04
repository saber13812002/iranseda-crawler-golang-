"""Session identity investigation — Class B quarantine (mission Stage 1).

Background
----------
A corpus record's public identity is ``record_id``, derived from the
EPG archive link when it carries ``?ch=&e=`` parameters:

    iranseda:ch{ch}:e{e}

but the production table ``radio_program_sessions`` enforces uniqueness
on ``(program_id, link)`` — NOT on ``link`` alone.  The same EPG link
can therefore legitimately exist under multiple programs, and every such
session maps to the SAME record_id.  The first session wins; the rest
fail batch validation ("duplicate record_id") and are written to
invalid.jsonl (the "Class B" quarantine).

This module is an INVESTIGATION tool.  It:

  * enumerates every (ch, e) group with more than one session;
  * compares the sessions on every available discriminator (program,
    filename/broadcast date, download state, SRT presence, status);
  * classifies each group into one of the mission's five categories;
  * emits a machine-readable JSONL result + a summary;
  * NEVER merges, deletes, or reclassifies anything.  The quarantine
    stays in force until a human adjudicates a group.

Identity architecture (Stage 1 §1.4) — the four entities this module
reasons about (documented, NOT yet a schema change):

  program_id          radio_programs.id (stable, PK)
  session_id          radio_program_sessions.id (stable, PK)
  episode_id          NOT yet established — a group may or may not be a
                      single archive episode; only human adjudication
                      may introduce one
  source_episode_key  (ch, e) parsed from the archive URL — identity of
                      the SOURCE, never the identity of a session

Quarantine policy (mission §1.3):
  * quarantined records keep their DB identifiers and content
    (invalid.jsonl holds the full record + problems);
  * a record is never promoted to valid merely because its URL matches;
  * (ch, e) is NEVER used as the sole identity of a session.
"""

import json
import hashlib
import datetime

from . import jalali

INVESTIGATION_VERSION = "1.0"

# Group categories (Stage 1 §1.2)
CAT_SAME_EP_MULTI_REF = "same_episode_multiple_references"
CAT_DIFF_SESSION_SHARED_LINK = "different_sessions_sharing_source_link"
CAT_SAME_PROGRAM_REPEATED_BROADCAST = "same_program_repeated_broadcast"
CAT_DIFF_PROGRAM_SHARED_ARCHIVE = "different_programs_shared_archive_reference"
CAT_INSUFFICIENT_EVIDENCE = "insufficient_evidence"


def _iso(v):
    if v is None:
        return None
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat()
    return str(v)


def _srt_candidates(disk, session):
    """SRT candidate (relpath, abspath) pairs, top-level first — mirrors
    mapper._resolve_original_srt (ground truth probe-14)."""
    from . import srt as _srtmod

    out = []
    srt_name = (session.get("srt_filename") or "").strip()
    audio_name = (session.get("filename") or "").strip()
    stem = jalali.stem_of(audio_name)
    if srt_name:
        for rel in ("downloads/%s" % srt_name,
                    "downloads/cleaned/%s" % srt_name):
            ab = disk.find(rel) if disk is not None else None
            if ab is not None:
                out.append((rel, ab))
    elif stem:
        for rel in ("downloads/%s.srt" % stem,
                    "downloads/cleaned/%s.srt" % stem):
            ab = disk.find(rel) if disk is not None else None
            if ab is not None:
                out.append((rel, ab))
    for rel, ab in out:
        try:
            with open(ab, "rb") as f:
                content = f.read(4096).decode("utf-8", "replace")
        except OSError:
            continue
        if _srtmod.looks_like_srt(content):
            return [rel, ab]
    return [out[0][0], out[0][1]] if out else [None, None]


def _srt_sha256(path):
    if path is None:
        return None
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def classify_group(members):
    """Classify one (ch, e) group into a mission category.

    members: list of session dicts (>=2) sharing one (ch, e).
    Deterministic; pure; returns one of the five CAT_* constants.

    Rules (most decisive first):
      * all filenames identical and non-None  -> same episode,
        multiple references (several DB rows point at the same
        archived file — likely one episode listed in more than one
        program);
      * exactly one program involved -> same program, repeated
        broadcast (the EPG slot reused across air dates; per the
        (program_id, link) unique constraint the rows are still
        distinct sessions);
      * more than one program involved -> different programs sharing
        one archive reference (the EPG link is shared; broadcast
        dates are recorded as evidence);
      * no filenames at all -> insufficient evidence.
    """
    if not members or len(members) < 2:
        return CAT_INSUFFICIENT_EVIDENCE

    fns = [m.get("filename") or None for m in members]
    pids = sorted({m.get("program_id") for m in members})

    if len(set(fns)) == 1 and fns[0] is None:
        return CAT_INSUFFICIENT_EVIDENCE
    if len(set(fns)) == 1:
        return CAT_SAME_EP_MULTI_REF
    if len(pids) == 1:
        return CAT_SAME_PROGRAM_REPEATED_BROADCAST
    return CAT_DIFF_PROGRAM_SHARED_ARCHIVE


def _gid_sort_key(g):
    """Stable ordering by (ch, e). g: group dict with ch/e."""
    e = g.get("e")
    try:
        ek = (0, int(e))
    except (TypeError, ValueError):
        ek = (1, str(e))
    return (g.get("ch") if g.get("ch") is not None else -1, ek)


def investigate(db, disk=None, log=None):
    """Full Class B investigation over the live sessions table.

    db:   corpus.database.Database (connected) or any object with
          fetch_sessions() -> (total, generator) and parse_ch/parse_e
          (class- or instance-level callables).
    disk: optional DiskIndex (enables SRT sha256 comparison)
    log:  callable, default print

    Returns {"summary": dict, "groups": [dict, ...]}.  Deterministic
    for an unchanged source: same groups, same categories, same order
    (groups sorted by (ch, e); members by session id).
    """
    log = log or (lambda *a: None)
    total, gen = db.fetch_sessions()
    groups = {}
    n_sessions = 0
    for s in gen:
        n_sessions += 1
        ch = db.parse_ch(s.get("link"))
        e = db.parse_e(s.get("link"))
        if ch is None or e is None:
            continue
        gid = "ch%d:e%s" % (ch, e)
        groups.setdefault(gid, {"ch": ch, "e": str(e), "members": []})
        groups[gid]["members"].append(s)

    colliding = [g for g in groups.values() if len(g["members"]) > 1]
    colliding.sort(key=_gid_sort_key)

    records = [_build_group_record(g, disk) for g in colliding]
    summary = _finalize(records, n_sessions)
    log("identity: %d sessions, %d (ch,e) groups with >1 session, %d sessions in groups"
        % (n_sessions, len(records),
           sum(r["member_count"] for r in records)))
    return {"summary": summary, "groups": records}


def _build_group_record(g, disk):
    """One JSONL line: the colliding (ch, e) group, fully preserved."""
    ch, e = g["ch"], g["e"]
    record_id = "iranseda:ch%d:e%s" % (ch, e)
    members = sorted(g["members"], key=lambda m: int(m.get("id") or 0))
    pids = sorted({m.get("program_id") for m in members
                   if m.get("program_id") is not None})
    fns = sorted({m.get("filename") or "" for m in members})
    statuses = sorted({m.get("status") or "" for m in members})
    n_downloaded = sum(1 for m in members if m.get("is_downloaded"))
    n_subtitled = sum(1 for m in members if m.get("is_subtitled"))

    srt_shas = set()
    srt_seen = 0
    members_out = []
    for m in members:
        stem = jalali.stem_of(m.get("filename") or "")
        b = jalali.parse_broadcast(stem)
        rel, ab = _srt_candidates(disk, m)
        if ab is not None:
            srt_seen += 1
            h = _srt_sha256(ab)
            if h:
                srt_shas.add(h)
        members_out.append({
            "session_id": int(m.get("id") or 0),
            "program_id": m.get("program_id"),
            "link": m.get("link"),
            "filename": m.get("filename") or None,
            "srt_filename": (m.get("srt_filename") or "").strip() or None,
            "srt_found": ab is not None,
            "broadcast_jalali": b["jalali"] if b else None,
            "broadcast_gregorian": b["gregorian"] if b else None,
            "status": m.get("status"),
            "is_downloaded": bool(m.get("is_downloaded")),
            "is_subtitled": bool(m.get("is_subtitled")),
            "attempts": m.get("attempts"),
            "created_at": _iso(m.get("created_at")),
            "updated_at": _iso(m.get("updated_at")),
            "srt_sha256": _srt_sha256(ab) if ab is not None else None,
        })

    return {
        "investigation_version": INVESTIGATION_VERSION,
        "group_key": "ch%d:e%s" % (ch, e),
        "record_id": record_id,
        "ch": ch,
        "e": str(e),
        "member_count": len(members),
        "session_ids": [m["session_id"] for m in members_out],
        "program_ids": pids,
        "filenames": fns,
        "broadcast_dates_jalali": sorted({m["broadcast_jalali"]["date"]
                                          for m in members_out
                                          if m["broadcast_jalali"]}),
        "statuses": statuses,
        "n_downloaded": n_downloaded,
        "n_subtitled": n_subtitled,
        "srt_sha256_distinct": sorted(srt_shas),
        "category": classify_group(members),
        "evidence": {
            "all_filenames_identical": len(fns) == 1,
            "program_count": len(pids),
            "distinct_broadcast_dates": len(set(
                m["broadcast_jalali"]["date"] for m in members_out
                if m["broadcast_jalali"])),
            "srt_files_found": srt_seen,
            "srt_content_identical": len(srt_shas) <= 1,
            "note": (
                "category is evidence-based, NOT an adjudication; the "
                "quarantine policy stands until a human decides the "
                "canonical session per (ch, e)"
            ),
        },
        "members": members_out,
        "quarantine": {
            "policy": "PERMANENT_UNTIL_IDENTITY_PROVEN",
            "action_required": "human adjudication of canonical session_id",
            "records_affected": len(members),
            "preserved_in": "data/corpus/invalid.jsonl",
        },
    }


def _finalize(records, n_sessions):
    by_cat = {}
    for r in records:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
    summary = {
        "investigation_version": INVESTIGATION_VERSION,
        "sessions_total": n_sessions,
        "groups_total": len(records),
        "groups_by_category": by_cat,
        "sessions_in_groups": sum(r["member_count"] for r in records),
        "category_legend": {
            CAT_SAME_EP_MULTI_REF: "identical filename in every member -> likely one archive episode referenced by several DB rows (possibly across programs)",
            CAT_DIFF_SESSION_SHARED_LINK: "reserved: distinct sessions sharing one source link without a more specific pattern (not emitted by the current rules)",
            CAT_SAME_PROGRAM_REPEATED_BROADCAST: "one program, the EPG slot reused across air dates (distinct sessions per the (program_id, link) unique constraint)",
            CAT_DIFF_PROGRAM_SHARED_ARCHIVE: "several programs reference the same EPG archive link",
            CAT_INSUFFICIENT_EVIDENCE: "cannot classify with available fields (e.g. no filenames)",
        },
        "quarantine_policy": (
            "all records in these groups stay quarantined (invalid.jsonl) "
            "until identity is proven per group; this file is read-only "
            "evidence and applies no resolution"
        ),
    }
    return summary


def write_jsonl(result, path):
    """Write the machine-readable investigation result.

    Line 1: the summary.  Then one line per colliding group (stable order).
    """
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True) + "\n")
        for g in result["groups"]:
            f.write(json.dumps(g, ensure_ascii=False, sort_keys=True) + "\n")
    return path
