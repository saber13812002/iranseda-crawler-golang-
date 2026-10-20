#!/usr/bin/env python3
"""STEP 12 — Roshan ASR Pilot: post-processing.

Turns raw Roshan (asr-ismc-fa) transcription responses into the dual-ASR
dataset artifacts:
  - SRT (only when Roshan returns real segment timestamps; otherwise TEXT_ONLY)
  - full text (from the SRT, or from the raw text when TEXT_ONLY)
  - manifest (provenance + checksums)
  - asr_output DB row (additive table; Whisper is never touched)

Deterministic, no LLM. Never modifies Whisper SRT/TXT.

Usage (on server 53):
  cd dashboard && set -a && . ./dashboard.env && set +a
  ./venv/bin/python roshan_pilot.py finalize --session 3 --dir ../downloads/asr/roshan/3
  ./venv/bin/python roshan_pilot.py compare  --session 3 --dir ../downloads/asr/roshan/3
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# paths / db (reuses the project's pymysql + dashboard.env conventions)
# ---------------------------------------------------------------------------
def _load_env():
    env = {}
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def _db_conn():
    import pymysql
    env = _load_env()
    return pymysql.connect(
        host=os.environ.get("DB_HOST") or env.get("DB_HOST") or "127.0.0.1",
        port=int(os.environ.get("DB_PORT") or env.get("DB_PORT") or 3308),
        user=env.get("DB_USER", "n8nuser"),
        password=env.get("DB_PASS", ""),
        database=env.get("DB_NAME", "radio"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Roshan response parsing
# ---------------------------------------------------------------------------
def _parse_ts_ms(ts):
    """Accept seconds (float/int) or 'HH:MM:SS,mmm' / 'HH:MM:SS.mmm' -> ms."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return int(float(ts) * 1000)
    s = str(ts).strip().replace(",", ".")
    m = re.match(r"^(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)$", s)
    if not m:
        return None
    a, b, c = m.groups()
    h = int(a) if a else 0
    return int(h * 3600000 + int(b) * 60000 + float(c) * 1000)


def parse_roshan_response(raw_path):
    """Return dict: {text, segments:[{start_ms,end_ms,text}], has_timestamps, model, lang, duration_ms}"""
    with open(raw_path, encoding="utf-8") as f:
        data = json.load(f)
    segs_in = data.get("segments") or []
    segments = []
    for s in segs_in:
        if isinstance(s, dict):
            st = _parse_ts_ms(s.get("start", s.get("start_ms")))
            en = _parse_ts_ms(s.get("end", s.get("end_ms")))
            txt = s.get("text") or s.get("seg_text") or ""
            if txt is None:
                txt = ""
            segments.append({"start_ms": st, "end_ms": en, "text": str(txt).strip()})
        else:
            segments.append({"start_ms": None, "end_ms": None, "text": str(s).strip()})
    has_ts = any(s["start_ms"] is not None and s["end_ms"] is not None for s in segments)
    text = data.get("text") or ""
    return {
        "text": str(text).strip(),
        "segments": segments,
        "has_timestamps": has_ts,
        "model": data.get("model"),
        "language": data.get("language"),
        "duration_ms": _parse_ts_ms(data.get("duration")) if data.get("duration") is not None else None,
    }


def _srt_ts(ms):
    if ms is None:
        return "00:00:00,000"
    ms = max(0, int(ms))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(segments, offset_ms=0):
    """segments with local timestamps + offset -> SRT text. Drops non-timestamped rows."""
    lines, idx = [], 0
    for s in segments:
        if s["start_ms"] is None or s["end_ms"] is None:
            continue
        st = s["start_ms"] + offset_ms
        en = s["end_ms"] + offset_ms
        if en <= st:
            continue
        if not s["text"]:
            continue
        idx += 1
        lines.append(str(idx))
        lines.append(f"{_srt_ts(st)} --> {_srt_ts(en)}")
        lines.append(s["text"])
        lines.append("")
    return "\n".join(lines)


def srt_to_fulltext(srt_text):
    """Extract the text lines (skip index + timestamp lines) -> full text."""
    out = []
    for line in srt_text.splitlines():
        line = line.strip()
        if not line or line.isdigit() or "-->" in line:
            continue
        out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# merge chunked results (STEP 12.6) — deterministic global timestamps + dedup
# ---------------------------------------------------------------------------
def merge_chunks(chunk_results):
    """chunk_results: list of (raw_path, start_ms) in time order.
    Returns {segments (global), text, needs_review:[...]}."""
    all_segs = []
    review = []
    for raw_path, start_ms in chunk_results:
        pr = parse_roshan_response(raw_path)
        if not pr["has_timestamps"]:
            review.append(f"{os.path.basename(raw_path)}: TEXT_ONLY chunk (no timestamps)")
            continue
        for s in pr["segments"]:
            if s["start_ms"] is None or s["end_ms"] is None:
                continue
            all_segs.append({
                "start_ms": s["start_ms"] + start_ms,
                "end_ms": s["end_ms"] + start_ms,
                "text": s["text"],
            })
    all_segs.sort(key=lambda s: s["start_ms"])
    # deterministic dedup: drop a segment if its [start,end) is contained in a
    # previous segment's span AND the text is a near-duplicate (overlap region).
    deduped, last = [], None
    for s in all_segs:
        if last is not None and s["start_ms"] < last["end_ms"]:
            if s["text"] and last["text"] and (
                s["text"] in last["text"] or last["text"] in s["text"]
                or _jaccard(s["text"], last["text"]) > 0.8
            ):
                last["end_ms"] = max(last["end_ms"], s["end_ms"])
                continue
        deduped.append(s)
        last = s
    text = "\n".join(s["text"] for s in deduped if s["text"])
    return {"segments": deduped, "text": text, "needs_review": review}


def _jaccard(a, b):
    wa, wb = set(re.findall(r"\S+", a)), set(re.findall(r"\S+", b))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


# ---------------------------------------------------------------------------
# validation (STEP 12.9 required tests)
# ---------------------------------------------------------------------------
def validate_srt(srt_text, fulltext):
    errs = []
    if not srt_text.strip():
        errs.append("empty SRT")
    if not fulltext.strip():
        errs.append("empty fulltext")
    # UTF-8 / Persian
    try:
        srt_text.encode("utf-8")
    except UnicodeEncodeError:
        errs.append("not valid UTF-8")
    if not re.search(r"[\u0600-\u06FF]", fulltext):
        errs.append("no Persian characters found")
    # chronological + non-negative
    blocks = re.split(r"\n\s*\n", srt_text.strip())
    prev_end = -1
    for b in blocks:
        ls = [x for x in b.splitlines() if x.strip()]
        if len(ls) < 2:
            continue
        m = re.match(r"(\d+:\d+:\d+,\d+) --> (\d+:\d+:\d+,\d+)", ls[1])
        if not m:
            continue
        st, en = _parse_ts_ms(m.group(1)), _parse_ts_ms(m.group(2))
        if st is None or en is None or st < 0:
            errs.append(f"invalid/negative timestamp: {ls[1]}")
        if en <= st:
            errs.append(f"inverted interval: {ls[1]}")
        if st < prev_end - 2000:  # >2s back -> ordering break
            errs.append(f"chronological break at {ls[1]}")
        prev_end = max(prev_end, en)
    return errs


# ---------------------------------------------------------------------------
# DB writer (STEP 12.8)
# ---------------------------------------------------------------------------
def save_asr_output(session_id, program_id, provider, model_name, model_version,
                    pipeline_version, audio_sha256, status, srt_path, fulltext_path,
                    raw_path, duration_ms, segment_count, word_count, latency_ms,
                    rtf=None, error_code=None, error_message=None):
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO asr_output
                 (session_id, program_id, provider, model_name, model_version,
                  pipeline_version, audio_sha256, processing_status, srt_path,
                  fulltext_path, raw_response_path, duration_ms, segment_count,
                  word_count, latency_ms, rtf, error_code, error_message)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                 ON DUPLICATE KEY UPDATE
                  processing_status=VALUES(processing_status),
                  srt_path=VALUES(srt_path), fulltext_path=VALUES(fulltext_path),
                  raw_response_path=VALUES(raw_response_path),
                  duration_ms=VALUES(duration_ms), segment_count=VALUES(segment_count),
                  word_count=VALUES(word_count), latency_ms=VALUES(latency_ms),
                  rtf=VALUES(rtf), error_code=VALUES(error_code),
                  error_message=VALUES(error_message), updated_at=NOW()""",
                (session_id, program_id, provider, model_name, model_version,
                 pipeline_version, audio_sha256, status, srt_path, fulltext_path,
                 raw_path, duration_ms, segment_count, word_count, latency_ms,
                 rtf, error_code, error_message),
            )
            new_id = cur.lastrowid
        conn.commit()
        return new_id
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# finalize: given a raw response (or merged chunks), write SRT/full/manifest/DB
# ---------------------------------------------------------------------------
def finalize(args):
    d = os.path.abspath(args.dir)
    run_id = f"roshan-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    audio = os.path.join(d, args.audio)
    audio_sha = sha256_file(audio) if os.path.exists(audio) else None

    # decide source: merged chunks or single raw
    if args.merge_chunks:
        pairs = []
        for spec in args.merge_chunks.split(","):
            raw, off = spec.split("=")
            pairs.append((os.path.join(d, raw), int(float(off) * 1000)))
        merged = merge_chunks(pairs)
        segments = merged["segments"]
        has_ts = any(s["start_ms"] is not None for s in segments)
        raw_path = os.path.join(d, "chunks-merged.raw.json")
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump({"merged_from": [p for p, _ in pairs],
                       "segments": segments, "needs_review": merged["needs_review"]},
                      f, ensure_ascii=False, indent=1)
    else:
        raw_path = os.path.join(d, args.raw)
        pr = parse_roshan_response(raw_path)
        segments = pr["segments"]
        has_ts = pr["has_timestamps"]

    prefix = f"roshan.{args.version}"
    srt_path = os.path.join(d, prefix + ".srt")
    full_path = os.path.join(d, prefix + ".full.txt")

    if has_ts:
        srt = build_srt(segments)
        status = "done"
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt)
        fulltext = srt_to_fulltext(srt)
        errs = validate_srt(srt, fulltext)
    else:
        srt = None
        status = "text_only"
        fulltext = (pr["text"] if not args.merge_chunks else merged["text"])
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(fulltext + "\n")
        errs = []
        if args.merge_chunks:
            errs += ["needs_review: " + r for r in merged.get("needs_review", [])]

    if status == "done":
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(fulltext + "\n")

    wc = len(fulltext.split())
    seg_count = len([s for s in segments if s.get("start_ms") is not None])
    duration_ms = None
    try:
        import subprocess
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", audio], text=True).strip()
        duration_ms = int(float(out) * 1000)
    except Exception:
        pass

    # latency: from run_log if available
    latency_ms = None
    rl = os.path.join(d, "run_log.jsonl")
    if os.path.exists(rl):
        try:
            for line in open(rl, encoding="utf-8"):
                j = json.loads(line)
                if j.get("event") in ("format", "chunk", "full", "probe"):
                    if j.get("http") == 200 and j.get("elapsed_s"):
                        latency_ms = int(float(j["elapsed_s"]) * 1000)
        except Exception:
            pass
    rtf = (latency_ms / duration_ms) if (latency_ms and duration_ms) else None

    # manifest
    manifest = {
        "run_id": run_id,
        "session_id": args.session,
        "provider": "roshan",
        "model_name": args.model,
        "pipeline_version": args.version,
        "audio": os.path.basename(audio),
        "audio_sha256": audio_sha,
        "status": status,
        "srt_path": os.path.basename(srt_path) if srt else None,
        "fulltext_path": os.path.basename(full_path),
        "raw_response_path": os.path.basename(raw_path),
        "segment_count": seg_count,
        "word_count": wc,
        "duration_ms": duration_ms,
        "latency_ms": latency_ms,
        "rtf": rtf,
        "validation_errors": errs,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(os.path.join(d, prefix + ".manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    new_id = save_asr_output(
        session_id=args.session, program_id=args.program, provider="roshan",
        model_name=args.model, model_version=args.model_version,
        pipeline_version=args.version, audio_sha256=audio_sha, status=status,
        srt_path=srt_path if srt else None, fulltext_path=full_path,
        raw_path=raw_path, duration_ms=duration_ms, segment_count=seg_count,
        word_count=wc, latency_ms=latency_ms, rtf=rtf,
        error_code=",".join(errs)[:60] if errs else None,
        error_message="; ".join(errs)[:500] if errs else None,
    )
    print(json.dumps({"run_id": run_id, "status": status, "db_id": new_id,
                      "srt": srt_path if srt else None, "full": full_path,
                      "raw": raw_path, "segments": seg_count, "words": wc,
                      "validation_errors": errs}, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------------------
# compare: Whisper vs Roshan side-by-side (STEP 12.10)
# ---------------------------------------------------------------------------
def _srt_blocks(path):
    blocks = {}
    cur = None
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.strip().isdigit():
            cur = int(line.strip())
            blocks[cur] = {"idx": cur, "ts": "", "text": ""}
        elif "-->" in line:
            blocks[cur]["ts"] = line.strip()
        elif line.strip() and cur:
            blocks[cur]["text"] = (blocks[cur]["text"] + " " + line.strip()).strip()
    return [blocks[k] for k in sorted(blocks)]


def compare(args):
    d = os.path.abspath(args.dir)
    wdir = os.path.abspath(args.whisper_dir)
    stem = f"radio-maaref-03-08-17-21-30"
    wsrt = os.path.join(wdir, stem + ".srt")
    rsrt = os.path.join(d, f"roshan.{args.version}.srt")
    wb = _srt_blocks(wsrt)
    rb = _srt_blocks(rsrt) if os.path.exists(rsrt) else []
    report = {
        "whisper_segments": len(wb),
        "roshan_segments": len(rb),
        "whisper_words": sum(len(b["text"].split()) for b in wb),
        "roshan_words": sum(len(b["text"].split()) for b in rb),
        "side_by_side": [],
    }
    # align by nearest timestamp
    for b in wb[:60]:
        m = re.match(r"(\d+):(\d+):(\d+)", b["ts"])
        if not m:
            continue
        t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        best = min((r for r in rb if r["ts"]), key=lambda r: abs(_ts_t(r["ts"]) - t), default=None)
        report["side_by_side"].append({
            "time": f"{m.group(1)}:{m.group(2)}:{m.group(3)}",
            "whisper": b["text"],
            "roshan": best["text"] if best else "(no segment)",
        })
    with open(os.path.join(d, f"compare_{args.version}.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: report[k] for k in ("whisper_segments", "roshan_segments",
                                              "whisper_words", "roshan_words")}, indent=1))
    print(f"side-by-side written to {os.path.join(d, 'compare_' + args.version + '.json')}")


def _ts_t(ts):
    m = re.match(r"(\d+):(\d+):(\d+)", ts)
    if not m:
        return 0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("finalize")
    f.add_argument("--session", type=int, required=True)
    f.add_argument("--program", type=int, default=1)
    f.add_argument("--dir", required=True)
    f.add_argument("--audio", default="radio-maaref-03-08-17-21-30.mp3")
    f.add_argument("--raw", default="sample_90s.mp3.raw.json")
    f.add_argument("--model", default="asr-ismc-fa")
    f.add_argument("--model-version", default=None)
    f.add_argument("--version", default="v1")
    f.add_argument("--merge-chunks", default=None, help="raw1=offset1s,raw2=offset2s,...")
    c = sub.add_parser("compare")
    c.add_argument("--session", type=int, required=True)
    c.add_argument("--dir", required=True)
    c.add_argument("--whisper-dir", default="../downloads")
    c.add_argument("--version", default="v1")
    a = ap.parse_args()
    if a.cmd == "finalize":
        finalize(a)
    elif a.cmd == "compare":
        compare(a)


if __name__ == "__main__":
    main()
