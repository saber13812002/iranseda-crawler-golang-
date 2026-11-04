"""SRT parsing (pure stdlib, tolerant of the two live timestamp formats).

Live formats observed on 53:
  * original SRTs:     HH:MM:SS,mmm --> HH:MM:SS,mmm
  * corrected SRTs:    H:MM:SS --> H:MM:SS        (no milliseconds)

Both are accepted by the exporter's parser and validator.
"""

import re

_TS_RE = re.compile(r"^(\d{1,3}):(\d{1,2}):(\d{1,2})(?:[,.](\d{1,3}))?$")


def ts_to_seconds(ts):
    """'HH:MM:SS,mmm' / 'H:MM:SS' -> float seconds, or None if invalid."""
    if not ts:
        return None
    m = _TS_RE.match(str(ts).strip())
    if not m:
        return None
    h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
    ms = m.group(4)
    if mi > 59 or s > 59:
        return None
    frac = 0.0
    if ms:
        frac = int(ms.ljust(3, "0")) / 1000.0
    return h * 3600.0 + mi * 60.0 + s + frac


def parse_srt(content):
    """Parse SRT content into a list of cues.

    Returns (cues, error). cue = {"index": int|None, "start": float|None,
    "end": float|None, "text": str}. error is None when the content looks
    like SRT (at least one cue with a valid timing line), else a string.
    """
    if content is None:
        return [], "empty content"
    text = str(content)
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cues = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        # a cue starts with an optional numeric index line, then a timing line
        idx = None
        j = i
        if line.isdigit():
            idx = int(line)
            j = i + 1
        if j >= n:
            break
        timing = lines[j].strip()
        if "-->" in timing:
            start_s, end_s = timing.split("-->", 1)
            start = ts_to_seconds(start_s)
            end = ts_to_seconds(end_s)
            if start is None or end is None:
                i = j + 1
                continue
            i = j + 1
            body = []
            while i < n and lines[i].strip() != "":
                body.append(lines[i].strip())
                i += 1
            cues.append({
                "index": idx,
                "start": start,
                "end": end,
                "text": " ".join(b for b in body if b),
            })
        else:
            i += 1
    if not cues:
        return [], "no valid cue timing lines found"
    return cues, None


def srt_stats(content):
    """(segment_count, duration_sec) for an SRT string; (None, None) when
    unparseable."""
    cues, err = parse_srt(content)
    if err:
        return None, None
    duration = max(c["end"] for c in cues if c["end"] is not None)
    return len(cues), round(duration, 3)


def srt_to_text(content):
    """SRT -> plain text (cue texts concatenated, one per line). Used for
    TXT derivation checks, not for corpus output (TXT files are disk
    artifacts in prod)."""
    cues, err = parse_srt(content)
    if err:
        return None
    return "\n".join(c["text"] for c in cues if c["text"])


def looks_like_srt(content):
    _, err = parse_srt(content)
    return err is None
