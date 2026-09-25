"""
Whisper service API (OpenAI-compatible audio endpoint + queue helpers).

Endpoints:
  GET  /health               - liveness + model state
  GET  /v1/models            - model list (OpenAI-style)
  POST /v1/audio/transcriptions
        - OpenAI-compatible: multipart file upload OR {"url": "..."}
        - response: {"text": ..., "srt": ...}
  GET  /queue?status=pending_transcribe - sessions waiting in the DB
  POST /queue/claim?limit=N - worker claims N pending sessions (CAS-safe)
"""
import os
import tempfile
import time

import requests
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

import common

app = FastAPI(title="IranSeda Whisper Service")

_state = {"model": None, "loaded_at": None}


def _ensure_model():
    if _state["model"] is None:
        _state["model"] = common.get_model()
        _state["loaded_at"] = time.time()


@app.on_event("startup")
def _startup():
    _ensure_model()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_loaded": _state["model"] is not None,
        "model": os.getenv("WHISPER_MODEL", "large-v3-turbo"),
        "device": os.getenv("WHISPER_DEVICE", "cuda"),
    }


@app.get("/v1/models")
def models():
    name = os.getenv("WHISPER_MODEL", "large-v3-turbo")
    return {"object": "list", "data": [{"id": name, "object": "model", "owned_by": "local"}]}


@app.post("/v1/audio/transcriptions")
async def transcriptions(
    file: UploadFile = File(None),
    url: str = Query(None),
    model: str = Query(None),
    language: str = Query(None),
    response_format: str = Query("text"),
):
    if not file and not url:
        raise HTTPException(400, "provide a file upload or a 'url' query param")
    tmp_path = None
    try:
        if file:
            suffix = os.path.splitext(file.filename or "audio")[1] or ".mp4"
            fd, tmp_path = tempfile.mkstemp(suffix=suffix)
            with os.fdopen(fd, "wb") as f:
                f.write(await file.read())
        else:
            audio = common.download_media(url, tempfile.mkdtemp(prefix="ws_"))
            tmp_path = audio
        _ensure_model()
        srt_text = common.transcribe_to_srt(tmp_path, language=language, model_name=model)
        full_text = " ".join(
            block.strip().split("\n")[-1] for block in srt_text.strip().split("\n\n")
        )
        return {"text": full_text, "srt": srt_text}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"transcription failed: {exc}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
            parent = os.path.dirname(tmp_path)
            if parent.startswith(tempfile.gettempdir()) and not os.listdir(parent):
                os.rmdir(parent)


@app.get("/queue")
def queue(status: str = Query("pending_transcribe")):
    conn = common.db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, link, filename, status, attempts, last_error,
                       (SELECT p.name FROM radio_programs p WHERE p.id = program_id) AS program
                FROM radio_program_sessions
                WHERE status = %s
                ORDER BY id
                LIMIT 200
                """,
                (status,),
            )
            rows = cur.fetchall()
            cur.execute("SELECT status, COUNT(*) AS n FROM radio_program_sessions GROUP BY status")
            by_status = {r["status"]: r["n"] for r in cur.fetchall()}
        return {"items": rows, "by_status": by_status}
    finally:
        conn.close()


@app.post("/queue/claim")
def claim(limit: int = Query(1, ge=1, le=20)):
    """Atomically claim N pending sessions for a worker (sets status='transcribing')."""
    conn = common.db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM radio_program_sessions
                WHERE status = 'pending_transcribe'
                ORDER BY id
                LIMIT %s
                FOR UPDATE
                """,
                (limit,),
            )
            ids = [r["id"] for r in cur.fetchall()]
            if ids:
                placeholders = ",".join(["%s"] * len(ids))
                cur.execute(
                    f"UPDATE radio_program_sessions SET status = 'transcribing' WHERE id IN ({placeholders})",
                    ids,
                )
        conn.commit()
        return {"claimed": ids}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@app.post("/queue/result")
def queue_result(
    session_id: int,
    success: bool,
    srt_filename: str = None,
    mp3_filename: str = None,
    error: str = None,
    copy_to_52: bool = Query(True),
):
    """Worker reports the outcome of one session and (optionally) ships SRT/MP4 to server 52."""
    conn = common.db_conn()
    try:
        with conn.cursor() as cur:
            if success:
                cur.execute(
                    """
                    UPDATE radio_program_sessions
                    SET status = 'subtitled', is_downloaded = 1, is_subtitled = 1,
                        srt_filename = %s,
                        filename = IF(filename IS NULL OR filename = '', %s, filename),
                        last_error = NULL
                    WHERE id = %s
                    """,
                    (srt_filename, mp3_filename, session_id),
                )
                if copy_to_52:
                    _copy_files_to_52(srt_filename, mp3_filename)
            else:
                cur.execute(
                    """
                    UPDATE radio_program_sessions
                    SET status = 'failed', attempts = attempts + 1, last_error = %s
                    WHERE id = %s
                    """,
                    ((error or "unknown error")[:500], session_id),
                )
        conn.commit()
        return {"ok": True, "session_id": session_id, "status": "subtitled" if success else "failed"}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _copy_files_to_52(srt_filename, mp3_filename):
    """SRT always; MP4 only when KEEP_MP4=1. LAN ssh to server 52."""
    import subprocess

    dest = os.getenv("REMOTE_DOWNLOADS", "/home/saber/saberprojects/iranseda/downloads")
    src = os.getenv("WORK_DIR", "/tmp/whisper-worker")
    keep_mp4 = os.getenv("KEEP_MP4", "0") == "1"
    files = []
    if srt_filename:
        files.append(os.path.join(src, srt_filename))
    if mp3_filename and keep_mp4:
        files.append(os.path.join(src, mp3_filename))
    if not files:
        return
    existing = [f for f in files if os.path.exists(f)]
    if not existing:
        return
    cmd = [
        "scp", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
        "-o", "StrictHostKeyChecking=no",
        *existing,
        f"{os.getenv('SSH_TARGET', 'saber@172.20.1.52')}:{dest}/",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if res.returncode != 0:
        raise RuntimeError(f"scp to 52 failed: {res.stderr[:300]}")
