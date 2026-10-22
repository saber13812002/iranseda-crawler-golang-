#!/usr/bin/env python3
"""RADIO RAG — FULL RUN: build a versioned, session-keyed retrieval dump.

Reuses the pilot's proven date-parsing (extract.py) and chunking (chunk.py)
but drives over ALL mp4+subtitled sessions, keyed on **session_id** (not the
filename stem) so the 652 re-run/simulcast collisions are preserved as
distinct documents. Output is the full corpus for embedding.

Read-only on MySQL + files. No secrets, no modifications.

Output (on the build host):
  full_dump/dump_v2.jsonl     one JSON per chunk (retrieval corpus)
  full_dump/manifest_v2.json  counts, per-episode chunk counts, sha256, params
  full_dump/episodes_v2.jsonl one JSON per session (the "standard JSON", full)
"""
import json, os, re, sys, time, hashlib
from collections import Counter, defaultdict

import extract as EX
import chunk as CK

SCHEMA_VERSION = "2.0"
DUMP_VERSION = "2.0"


def stem_of(fn: str) -> str:
    for ext in (".mp4", ".srt", ".txt"):
        if fn.endswith(ext):
            fn = fn[:-len(ext)]
    return fn


def _clean(v):
    """Strip control chars AND literal escape sequences from a DB metadata
    field. Some program names carry the feed's trailing marker as the LITERAL
    two-char sequences '\\n' and '\\t' (not real newline bytes), e.g.
    'امیر مؤمنان\\n\\n\\t\\t\\t\\t\\t' -> 'امیر مؤمنان'."""
    if v is None:
        return None
    s = str(v)
    # literal backslash-escape sequences first (feed artifact), then real control chars
    s = s.replace("\\n", " ").replace("\\t", " ").replace("\\r", " ")
    s = s.replace("\t", " ").replace("\r", " ").replace("\n", " ")
    s = re.sub(r" {2,}", " ", s).strip()
    return s or None


def main(out_root: str):
    os.makedirs(out_root, exist_ok=True)
    t0 = time.time()

    # ---- 1. read sessions (clean 4-col rows), programs (separate, tail-safe),
    #          llm. Querying sessions WITHOUT the JOIN avoids a multi-line
    #          description corrupting session-row alignment (splitlines).
    sess_rows = EX.mysql_query(
        "SELECT id, program_id, filename, created_at FROM radio_program_sessions "
        "WHERE status='subtitled' AND filename LIKE '%mp4%'")

    # programs by id; name+time_description first (safe), description/channel LAST
    # so a multi-line description only extends the tail, never shifting earlier cols.
    prog_rows = EX.mysql_query(
        "SELECT id, name, time_description, radio, description FROM radio_programs")
    prog_by_id = {}
    for row in prog_rows:
        f = row.split("\t")
        if len(f) < 5:
            f = f + ["NULL"] * (5 - len(f))
        prog_by_id[f[0]] = {
            "name": f[1] if f[1] != "NULL" else None,
            "tdesc": f[2] if f[2] != "NULL" else None,
            "channel": f[3] if f[3] != "NULL" else None,
            "pdesc": "\t".join(f[4:]) if f[4] != "NULL" else None,  # rejoin tail
        }

    llm = EX.mysql_query(
        "SELECT session_id, job_type, LENGTH(content), LENGTH(content_en), "
        "LENGTH(srt_content), status FROM llm_output")
    llm_by_session = defaultdict(dict)
    for row in llm:
        f = row.split("\t")
        if len(f) < 6:
            f = f + ["NULL"] * (6 - len(f))
        llm_by_session[int(f[0])][f[1]] = {
            "content_len": int(f[2]) if f[2] not in ("NULL", "") else 0,
            "content_en_len": int(f[3]) if f[3] not in ("NULL", "") else 0,
            "srt_len": int(f[4]) if f[4] not in ("NULL", "") else 0,
            "status": f[5],
        }

    # ---- 2. group by session_id (one doc per session) ----
    #    but chunking is per-file; if a stem maps to >1 session, each session
    #    gets its own doc_id (session-scoped) and its own chunk set (same SRT
    #    content is fine — we cite the session's air date).
    sessions = []  # one dict per session
    for row in sess_rows:
        f = row.split("\t")
        if len(f) < 4:
            f = f + ["NULL"] * (4 - len(f))
        sid, pid, fn, created_at = f[0], f[1], f[2], f[3]
        pid = None if pid in ("NULL", "") else pid
        p = prog_by_id.get(pid, {}) if pid else {}
        stem = stem_of(fn)
        sessions.append({
            "session_id": int(sid), "program_id": pid,
            "filename": fn, "stem": stem, "created_at": created_at,
            "program_name": p.get("name"),
            "tdesc": p.get("tdesc"),
            "pdesc": p.get("pdesc"),
            "channel_name": p.get("channel"),
            "llm": llm_by_session.get(int(sid), {}),
        })

    # ---- 3. resolve air date per session (reuse pilot logic) ----
    #    Priority: (1) time_description, (2) legacy filename 2-digit year,
    #    (3) filename month/day + created_at year (approx).
    air_source_counts = Counter()
    eligible, no_air = 0, 0
    for s in sessions:
        stem = s["stem"]
        parsed = EX.parse_persian_date(stem)  # (ch, year, month, day, hh, mm, ss) or None
        tdesc = s["tdesc"] or ""
        td = EX.parse_time_description(tdesc)
        air = {}
        air_source = None
        if td:
            py, pm, pd = td["py"], td["pm"], td["pd"]
            hh, mm, ss = td["hh"], td["mm"], 0
            air_source = "time_description"
        elif parsed:
            ch, year, month, day, hh, mm, ss = parsed
            if year is None:
                year = EX.infer_year_from_created(s["created_at"])
                air_source = "filename+created_at"
            else:
                air_source = "filename"
            py, pm, pd = year, month, day
        else:
            py = pm = pd = hh = mm = ss = None
            air_source = "none"

        if air_source in ("none", None):
            no_air += 1
            s["air"] = None
            continue
        eligible += 1
        air_source_counts[air_source] += 1
        gy, gm, gd = EX.persian_to_gregorian(py, pm, pd)
        s["air"] = {
            "persian": f"{py:04d}-{pm:02d}-{pd:02d}",
            "gregorian": f"{gy:04d}-{gm:02d}-{gd:02d}",
            "time": f"{hh:02d}:{mm:02d}:{ss:02d}",
            "air_source": air_source,
            "created_at": s["created_at"],
            "note": EX._air_note(air_source, tdesc),
        }

    # ---- 4. build chunk docs (reuse chunk.make_episode_chunks) ----
    #    Build the episode dict in the shape make_episode_chunks expects, but
    #    with a session-scoped episode_id (doc_id) so collisions are distinct.
    ep_path_for_chunk = None  # chunk.py reads its own CL dir; we pass ep dict directly
    dump_path = os.path.join(out_root, "dump_v2.jsonl")
    eps_path = os.path.join(out_root, "episodes_v2.jsonl")
    total_chunks, total_chars = 0, 0
    per_ep = {}
    airless = 0
    with open(dump_path, "w", encoding="utf-8") as dd, \
         open(eps_path, "w", encoding="utf-8") as ee:
        for s in sessions:
            stem = s["stem"]
            # artifact presence
            srt_p = os.path.join(CK.CL, f"{stem}.correct.srt")
            if not os.path.exists(srt_p) and not os.path.exists(
                    os.path.join(EX.CL, stem + ".srt")):
                continue  # no subtitle content at all
            air = s.get("air")
            if air is None:
                # still emit a doc with air=null so the full set is accounted
                # (no fabrication); chunking proceeds using filename-only cite
                air = {"persian": "unknown", "gregorian": "unknown",
                       "time": "unknown", "air_source": "none",
                       "created_at": s["created_at"], "note": "no resolvable air date"}
                airless += 1

            episode_id = f"{stem}__s{s['session_id']}"
            # make_episode_chunks resolves the SRT path from ep["episode_id"],
            # so we must hand it the REAL stem (not the session-scoped id) to
            # find the file; we rewrite doc_id/chunk_id to the session id after.
            ep = {
                "episode_id": stem,
                "channel": f"radio-{(s['stem'].split('-')[1] if len(s['stem'].split('-'))>1 else 'maaref')}",
                "air": air,
                "program": {
                    "program_name": _clean(s["program_name"]),
                    "program_radio": _clean(s["channel_name"]),
                    "program_time_description": _clean(s["tdesc"]),
                    "program_description": _clean(s["pdesc"]),
                    "program_id": s["program_id"],
                },
                "source": {"db": "radio@172.20.1.53:3308",
                           "session_id": s["session_id"], "link": None,
                           "files_base": f"downloads/{stem}"},
                "artifacts": _artifacts(stem),
                "llm_metadata": s["llm"],
            }
            # write the session doc (session-scoped identity)
            ee.write(json.dumps({
                "schema_version": SCHEMA_VERSION,
                "episode_id": episode_id,
                "session_id": s["session_id"],
                "channel": ep["channel"],
                "air": air,
                "program": ep["program"],
                "source": ep["source"],
                "artifacts": ep["artifacts"],
                "content_hash": hashlib.sha256(
                    (stem + f":{s['session_id']}").encode()).hexdigest()[:16],
            }, ensure_ascii=False) + "\n")

            # chunks: make_episode_chunks reads CL/<stem>.correct.srt (stem above)
            n = 0
            for c in CK.make_episode_chunks(ep):
                # rewrite to the session-scoped doc id (collision-safe)
                c["doc_id"] = episode_id
                c["chunk_id"] = f"{episode_id}::{c['chunk_type']}::{n}"
                c["session_id"] = s["session_id"]
                c["schema_version"] = SCHEMA_VERSION
                dd.write(json.dumps(c, ensure_ascii=False) + "\n")
                total_chunks += 1
                total_chars += c["char_count"]
                n += 1
            per_ep[episode_id] = n

    # ---- 5. manifest ----
    dump_bytes = os.path.getsize(dump_path)
    with open(dump_path, "rb") as f:
        h = hashlib.sha256()
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    manifest = {
        "dump_version": DUMP_VERSION, "schema_version": SCHEMA_VERSION,
        "generated_at": "2026-10-22",
        "key": "session_id (collision-safe)",
        "params": {"chunk_window_sec": CK.CHUNK_WINDOW_SEC,
                   "max_chunk_chars": CK.MAX_CHUNK_CHARS,
                   "srt_source": "downloads/cleaned/<stem>.correct.srt",
                   "summary_sources": ["summary.txt", "summary.en.txt"]},
        "sessions_total": len(sessions),
        "sessions_eligible_air": eligible,
        "sessions_no_air": no_air,
        "air_source_counts": dict(air_source_counts),
        "episodes_written": len(per_ep),
        "episodes_airless": airless,
        "chunks": total_chunks, "chars": total_chars,
        "dump_file": "dump_v2.jsonl", "dump_bytes": dump_bytes,
        "dump_sha256": h.hexdigest(),
        "gen_seconds": round(time.time() - t0, 1),
    }
    with open(os.path.join(out_root, "manifest_v2.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(json.dumps(manifest, ensure_ascii=False, indent=1))


def _artifacts(stem: str) -> dict:
    a = {}
    for name, p in [("raw_srt", os.path.join(EX.CL, stem + ".srt")),
                    ("raw_txt", os.path.join(EX.CL, stem + ".txt")),
                    ("correct_srt", os.path.join(CK.CL, stem + ".correct.srt")),
                    ("correct_txt", os.path.join(CK.CL, stem + ".correct.txt")),
                    ("summary_fa", os.path.join(CK.CL, stem + ".summary.txt")),
                    ("summary_en", os.path.join(CK.CL, stem + ".summary.en.txt"))]:
        a[name] = os.path.exists(p)
    return a


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "full_dump")
    main(root)
