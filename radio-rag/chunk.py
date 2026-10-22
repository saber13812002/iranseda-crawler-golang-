#!/usr/bin/env python3
"""
RADIO RAG — STEP 1: chunk.py
Turn the standard episode JSON (state/pilot_episodes.json) into a versioned,
retrieval-ready dump + manifest.

Chunking policy
---------------
The retrieval unit is a window of consecutive SRT subtitle blocks from the
CLEANED subtitle file (downloads/cleaned/<stem>.correct.srt). Each chunk carries:
  - the program identity + air date (so a hit cites a real program + real time)
  - start_sec / end_sec  -> "from 00:01:20 to 00:01:50" citation
  - the concatenated subtitle text for the window
Chunk size target: ~300 seconds of audio per chunk, aligned to natural sentence
boundaries (we never split an SRT block; we split between blocks). A 30-min
program yields ~6 chunks. This keeps each chunk small enough for a tight
embedding yet long enough to carry real topical context.

We also emit one extra "summary" chunk per episode (the cleaned FA summary +
EN summary) so episode-level questions ("what was program X about?") are
answerable without scanning every 30-sec window.

Output (versioned)
------------------
  state/dump_v1.jsonl      one JSON object per chunk (the actual RAG corpus)
  state/manifest_v1.json   schema version, counts, per-episode chunk counts,
                           content hashes, generation params (idempotency check)

Idempotent: same episode JSON + same files -> byte-identical dump + manifest.
"""
import json, os, re, sys, hashlib, time
from datetime import timedelta

CL = "/home/saber/saberprojects/iranseda-crawler-golang-/downloads/cleaned"
SCHEMA_VERSION = "1.0"
DUMP_VERSION = "1.0"
CHUNK_WINDOW_SEC = 300   # soft time cap (~5 min of audio per chunk)
MAX_CHUNK_CHARS = 800    # primary driver: flush a chunk once it reaches this
MIN_CHUNK_CHARS = 200    # avoid tiny trailing chunks; merge back into previous


def _ts_to_sec(ts: str) -> int:
    """'0:00:03,240' or '00:01:02,000' -> seconds (int, floor)."""
    ts = ts.strip().rstrip(".")
    h, m, rest = ts.split(":")
    if "," in rest:
        s, frac = rest.split(",")
    else:
        s, frac = rest, "0"
    return int(h) * 3600 + int(m) * 60 + int(s)


def _split_long_text(text: str, max_chars: int):
    """Hard-split a single long string at word/space boundaries so no
    fragment exceeds max_chars. Used only for a single oversized SRT block
    (a real block that runs far past the chunk cap). Returns a list of
    fragments; the last may be shorter."""
    if len(text) <= max_chars:
        return [text]
    out, cur = [], ""
    for word in text.split(" "):
        if cur and len(cur) + 1 + len(word) > max_chars:
            out.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        out.append(cur)
    return out


def parse_srt(path: str):
    """-> list of {idx, start, end, text} blocks (start/end in seconds).

    A single SRT block whose text far exceeds MAX_CHUNK_CHARS (a malformed
    run where one timestamp swallowed a long stretch) is hard-split at word
    boundaries into several synthetic blocks sharing the same start/end, so
    the downstream windower can never emit a giant single-block chunk."""
    with open(path, encoding="utf-8", errors="replace") as f:
        raw = f.read()
    blocks, cur = [], None
    for line in raw.splitlines():
        line = line.rstrip()
        if line.isdigit():
            if cur is not None:
                blocks.append(cur)
            cur = {"idx": int(line), "start": 0, "end": 0, "text": []}
        elif "-->" in line and cur is not None:
            a, b = [x.strip() for x in line.split("-->")]
            cur["start"] = _ts_to_sec(a)
            cur["end"] = _ts_to_sec(b)
        elif line and cur is not None:
            cur["text"].append(line)
    if cur is not None:
        blocks.append(cur)
    out = []
    for b in blocks:
        b["text"] = " ".join(t for t in b["text"] if t)
        # hard-split any single block far past the cap (synthetic sub-blocks
        # inherit the same timing; citation range is preserved)
        if len(b["text"]) > MAX_CHUNK_CHARS * 2:
            for i, frag in enumerate(_split_long_text(b["text"], MAX_CHUNK_CHARS)):
                sub = dict(b)
                sub["idx"] = b["idx"] * 1000 + i
                sub["text"] = frag
                out.append(sub)
        else:
            out.append(b)
    return out


def read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _sec_hms(s: int) -> str:
    return str(timedelta(seconds=int(s)))


def _window_chunk(base: dict, window: list, prog: dict, air: dict, stem: str) -> dict:
    cstart, cend = window[0]["start"], window[-1]["end"]
    text = " ".join(b["text"] for b in window)
    d = dict(base)
    d.update(
        start_sec=cstart, end_sec=cend,
        start_hms=_sec_hms(cstart), end_hms=_sec_hms(cend),
        citation=(f"{prog.get('program_name') or stem}, "
                  f"air {air['persian']} ({air['gregorian']}), "
                  f"from {_sec_hms(cstart)} to {_sec_hms(cend)}"),
        text=text, char_count=len(text), srt_block_count=len(window),
    )
    return d


def make_episode_chunks(ep: dict):
    stem = ep["episode_id"]
    air = ep["air"]
    prog = ep["program"]
    base = dict(
        chunk_id=None,
        doc_id=stem,
        channel=ep["channel"],
        program_name=prog.get("program_name"),
        program_radio=prog.get("program_radio"),
        air_persian=air["persian"],
        air_gregorian=air["gregorian"],
        air_time=air["time"],
        air_source=air["air_source"],
        session_id=ep["source"]["session_id"],
        chunk_type="subtitle_window",
        language="fa",
        start_sec=0, end_sec=0,
        start_hms="00:00:00", end_hms="00:00:00",
        citation=None,
        text=None,
        char_count=0,
        srt_block_count=0,
    )

    srt_path = os.path.join(CL, f"{stem}.correct.srt")
    chunks = []
    if os.path.exists(srt_path):
        blocks = parse_srt(srt_path)
        # Group consecutive SRT blocks into chunks. A chunk flushes when it
        # reaches MAX_CHUNK_CHARS or spans more than CHUNK_WINDOW_SEC of audio.
        # Always align to block boundaries (never split a subtitle block).
        windows, window, win_chars, win_start = [], [], 0, 0
        for b in blocks:
            if window and (win_chars + len(b["text"]) > MAX_CHUNK_CHARS or
                           b["start"] - win_start > CHUNK_WINDOW_SEC):
                windows.append(window)
                window, win_chars, win_start = [], 0, b["start"]
            window.append(b)
            win_chars += len(b["text"])
        if window:
            # merge a tiny trailing window back into the previous one
            if windows and win_chars < MIN_CHUNK_CHARS:
                windows[-1].extend(window)
            else:
                windows.append(window)
        for c in windows:
            yield _window_chunk(base, c, prog, air, stem)
    # summary chunk (episode-level)
    fa_sum = read_text(os.path.join(CL, f"{stem}.summary.txt"))
    en_sum = read_text(os.path.join(CL, f"{stem}.summary.en.txt"))
    if fa_sum or en_sum:
        d = dict(base)
        text = (fa_sum + ("\n\n" + en_sum if en_sum else ""))
        d.update(
            chunk_type="summary", language="fa+en",
            citation=(f"{prog.get('program_name') or stem}, "
                      f"episode summary, air {air['persian']} ({air['gregorian']})"),
            text=text, char_count=len(text), srt_block_count=0,
        )
        yield d


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    ep_path = os.path.join(root, "state", "pilot_episodes.json")
    with open(ep_path, encoding="utf-8") as f:
        eps = json.load(f)["episodes"]

    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "state")
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()
    total_chunks, total_chars, per_ep = 0, 0, {}
    rows = []
    for ep in eps:
        n = 0
        for d in make_episode_chunks(ep):
            h = hashlib.sha256(
                (d["doc_id"] + "|" + d["chunk_type"] + "|" +
                 str(d["start_sec"]) + "|" + d["text"]).encode()).hexdigest()[:16]
            d["chunk_id"] = f"{d['doc_id']}::{d['chunk_type']}::{d['start_sec']}"
            d["content_hash"] = h
            d["schema_version"] = SCHEMA_VERSION
            rows.append(d)
            total_chunks += 1
            total_chars += d["char_count"]
            n += 1
        per_ep[ep["episode_id"]] = n

    dump_path = os.path.join(out_dir, "dump_v1.jsonl")
    with open(dump_path, "w", encoding="utf-8") as f:
        for d in rows:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    dump_bytes = os.path.getsize(dump_path)
    manifest = {
        "dump_version": DUMP_VERSION,
        "schema_version": SCHEMA_VERSION,
        "generated_at": "2026-10-22",
        "params": {"chunk_window_sec": CHUNK_WINDOW_SEC, "max_chunk_chars": MAX_CHUNK_CHARS,
                   "srt_source": "downloads/cleaned/<stem>.correct.srt",
                   "summary_sources": ["summary.txt", "summary.en.txt"]},
        "episodes": len(eps),
        "chunks": total_chunks,
        "chars": total_chars,
        "dump_file": "dump_v1.jsonl",
        "dump_bytes": dump_bytes,
        "per_episode_chunks": per_ep,
        "dump_sha256": hashlib.sha256(open(dump_path, "rb").read()).hexdigest(),
        "gen_seconds": round(time.time() - t0, 2),
    }
    with open(os.path.join(out_dir, "manifest_v1.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in manifest.items() if k != "per_episode_chunks"},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
