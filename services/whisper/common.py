"""Shared helpers for the whisper service (worker + API)."""
import os
import re
import urllib.parse

import faster_whisper
import pymysql
import requests
from faster_whisper.transcribe import Segment

DB_TIMEOUT = 10

# Where the crawler saves fetched media on the host. Mounted into the worker
# container so it can REUSE files instead of re-downloading them.
LOCAL_DOWNLOADS_DIR = os.getenv(
    "LOCAL_DOWNLOADS_DIR",
    "/home/saber/saberprojects/iranseda-crawler-golang-/downloads",
)

# Browser-like header. The radio.iranseda.ir epgarchivePart endpoint sits behind
# an anti-bot layer that returns a 15-byte doctype stub / 503 / connection reset
# to a plain python-requests default User-Agent.
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class LocalMediaMissing(Exception):
    """Media is not on disk and cannot be re-fetched (endpoint blocked/absent)."""


def db_conn():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3308")),
        user=os.getenv("DB_USER", "n8nuser"),
        password=os.getenv("DB_PASS"),
        database=os.getenv("DB_NAME", "radio"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=DB_TIMEOUT,
    )


def srt_for_segment(seg: Segment) -> str:
    """One SRT block for a faster-whisper segment (timestamps in seconds)."""
    return f"{int(seg.start)}_{int(seg.end)}"


def srt_ts(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{int((seconds - int(seconds)) * 1000):03d}"


def seg_to_srt_block(index: int, seg: Segment) -> str:
    return f"{index}\n{srt_ts(seg.start)} --> {srt_ts(seg.end)}\n{seg.text.strip()}\n"


def link_to_archive_page(link: str) -> str:
    """Session link (../epgarchivePart/?...) -> absolute radio.iranseda.ir page URL."""
    link = link.replace("..", "", 1)
    return "https://radio.iranseda.ir" + link


def extract_dl_url(page_html: str) -> str:
    """<a class='col-plus page-loding'> href is the direct file URL."""
    m = re.search(r'<a[^>]+class="[^"]*col-plus[^"]*"[^>]*href="([^"]+)"', page_html)
    return m.group(1).strip() if m else ""


def filename_from_content_disposition(headers) -> str:
    disp = headers.get("Content-Disposition", "")
    if "filename=" in disp:
        start = disp.index("filename=") + len("filename=")
        end = disp.find(";", start)
        name = disp[start:end if end != -1 else len(disp)].strip().strip('"')
        name = re.sub(r'[/:\s]+', "-", name)
        if name:
            return name
    # fallback: from the direct URL path
    return "download.bin"


def filename_from_link(link: str) -> str:
    """Fallback name when Content-Disposition is missing (from the e= id)."""
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
    e = qs.get("e", ["unknown"])[0]
    ch = qs.get("ch", ["0"])[0]
    return f"epg-ch{ch}-e{e}.mp4"


def find_local_media(filename: str, link: str, dest_dir: str = None) -> str:
    """
    Locate an already-downloaded media file without re-downloading.

    The crawler stores files (radio-<ch>-<date>-<time>.mp4) in LOCAL_DOWNLOADS_DIR.
    Prefer the DB-provided filename, then the name derived from the link.
    Returns an existing path, or '' when the file is not present.
    """
    dest_dir = dest_dir or LOCAL_DOWNLOADS_DIR
    candidates = []
    if filename:
        candidates.append(filename)
    candidates.append(filename_from_link(link))
    for name in candidates:
        p = os.path.join(dest_dir, name)
        try:
            if os.path.exists(p) and os.path.getsize(p) > 100_000:
                return p
        except OSError:
            continue
    return ""


def download_media(link: str, dest_dir: str, timeout: int = 120) -> str:
    """
    Download one session's media file; returns the local file path.

    Raises LocalMediaMissing when the file cannot be fetched (anti-bot stub,
    503, reset, or no link found) so the caller can hand the row back to the
    crawler instead of burning retry attempts.
    """
    page_url = link_to_archive_page(link)
    try:
        page = requests.get(page_url, timeout=30, headers={"User-Agent": UA})
        page.raise_for_status()
    except requests.RequestException as exc:
        raise LocalMediaMissing(f"archive page fetch failed: {type(exc).__name__}")
    html = page.text or ""
    if len(html) < 500:  # anti-bot stub (e.g. the 15-byte doctype) - not a real page
        raise LocalMediaMissing(f"archive page returned anti-bot stub ({len(html)} bytes)")
    dl_url = extract_dl_url(html)
    if not dl_url:
        raise LocalMediaMissing("no direct download link on archive page")
    if dl_url.startswith("/"):
        dl_url = "https://radio.iranseda.ir" + dl_url

    os.makedirs(dest_dir, exist_ok=True)
    try:
        with requests.get(dl_url, stream=True, timeout=timeout, headers={"User-Agent": UA}) as r:
            r.raise_for_status()
            name = filename_from_content_disposition(r.headers)
            if not name.endswith((".mp3", ".mp4")):
                name += ".mp4"
            path = os.path.join(dest_dir, name)
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    f.write(chunk)
    except requests.RequestException as exc:
        raise LocalMediaMissing(f"media download failed: {type(exc).__name__}")
    if os.path.getsize(path) < 100_000:  # sane minimum for a radio file
        raise LocalMediaMissing(f"downloaded file too small: {os.path.getsize(path)} bytes")
    return path


_model_cache = {}


def get_model(model_name: str = None, device: str = "cuda"):
    model_name = model_name or os.getenv("WHISPER_MODEL", "large-v3-turbo")
    key = (model_name, device)
    if key not in _model_cache:
        _model_cache[key] = faster_whisper.WhisperModel(
            model_name, device=device, compute_type=os.getenv("WHISPER_COMPUTE", "int8")
        )
    return _model_cache[key]


def transcribe_to_srt(audio_path: str, language: str = None, model_name: str = None) -> str:
    """Transcribe one media file, return SRT text."""
    language = language or os.getenv("WHISPER_LANGUAGE", "fa")
    model = get_model(model_name)
    segments, _info = model.transcribe(
        audio_path,
        language=language,
        beam_size=int(os.getenv("WHISPER_BEAM", "5")),
        vad_filter=True,
    )
    blocks = []
    for i, seg in enumerate(segments, 1):
        blocks.append(seg_to_srt_block(i, seg))
    return "\n".join(blocks)


def transcribe_to_text(audio_path: str, language: str = None, model_name: str = None) -> str:
    language = language or os.getenv("WHISPER_LANGUAGE", "fa")
    model = get_model(model_name)
    segments, _info = model.transcribe(
        audio_path, language=language,
        beam_size=int(os.getenv("WHISPER_BEAM", "5")), vad_filter=True,
    )
    return " ".join(seg.text.strip() for seg in segments)
