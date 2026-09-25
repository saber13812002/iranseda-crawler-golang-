"""Shared helpers for the whisper service (worker + API)."""
import os
import re
import urllib.parse

import faster_whisper
import pymysql
import requests
from faster_whisper.transcribe import Segment

DB_TIMEOUT = 10


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


def download_media(link: str, dest_dir: str, timeout: int = 300) -> str:
    """Download one session's media file; returns the local file path."""
    page = requests.get(link_to_archive_page(link), timeout=60)
    page.raise_for_status()
    dl_url = extract_dl_url(page.text)
    if not dl_url:
        raise RuntimeError("no direct download link on archive page")
    if dl_url.startswith("/"):
        dl_url = "https://radio.iranseda.ir" + dl_url

    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, filename_from_link(link))
    with requests.get(dl_url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        name = filename_from_content_disposition(r.headers)
        if not name.endswith((".mp3", ".mp4")):
            name += ".mp4"
        path = os.path.join(dest_dir, name)
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                f.write(chunk)
    if os.path.getsize(path) < 100_000:  # sane minimum for a radio file
        raise RuntimeError(f"downloaded file too small: {os.path.getsize(path)} bytes")
    return path


_model_cache = {}


def get_model(model_name: str = None, device: str = "cuda"):
    model_name = model_name or os.getenv("WHISPER_MODEL", "large-v3-turbo")
    key = (model_name, device)
    if key not in _model_cache:
        _model_cache[key] = faster_whisper.WhisperModel(
            model_name, device=device, compute_type="float16" if device == "cuda" else "int8"
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
