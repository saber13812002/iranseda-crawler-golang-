"""
Whisper queue worker (runs inside the GPU container on server 53).

Loop:
  1. pick next sessions (status = 'pending_transcribe')
  2. download media from radio.iranseda.ir (by session link)
  3. transcribe with faster-whisper (GPU)
  4. ship SRT (and optional MP4) to server 52 over LAN ssh
  5. report result -> DB (subtitled / failed with attempts + last_error)

Statuses:
  pending_transcribe  -> waiting in queue
  transcribing        -> being processed by a worker
  subtitled           -> SRT delivered to server 52
  failed              -> last attempt failed (attempts < MAX_ATTEMPTS), retried
  failed_permanent    -> parked after MAX_ATTEMPTS failures

Env:
  WORK_DIR      scratch dir (default /tmp/whisper-worker)
  BATCH_SIZE    how many to pull per DB read (default 1)
  KEEP_MP4      1 = also copy media to 52 (default 0, delete after)
  IDLE_SLEEP    seconds to sleep when queue empty (default 30)
  MAX_ATTEMPTS  failures before parking (default 3)
  DELAY_BETWEEN seconds between sessions (default 1)
"""
import logging
import os
import shutil
import subprocess
import sys
import time

import common

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")

WORK_DIR = os.getenv("WORK_DIR", "/tmp/whisper-worker")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1"))
IDLE_SLEEP = int(os.getenv("IDLE_SLEEP", "30"))
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "3"))
DELAY_BETWEEN = int(os.getenv("DELAY_BETWEEN", "1"))
KEEP_MP4 = os.getenv("KEEP_MP4", "0") == "1"
SSH_TARGET = os.getenv("SSH_TARGET", "saber@172.20.1.52")
REMOTE_DOWNLOADS = os.getenv("REMOTE_DOWNLOADS", "/home/saber/saberprojects/iranseda/downloads")
SSH_KEY = os.getenv("SSH_KEY_PATH", "")  # e.g. /app/keys/id_ed25519 (mounted in container)


def _next_sessions(limit: int):
    conn = common.db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, link, attempts FROM radio_program_sessions
                WHERE status = 'pending_transcribe'
                ORDER BY id LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
            for r in rows:
                cur.execute(
                    "UPDATE radio_program_sessions SET status = 'transcribing' WHERE id = %s",
                    (r["id"],),
                )
        conn.commit()
        return rows
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _finish(sid: int, ok: bool, srt_filename=None, mp4_filename=None, error=None):
    conn = common.db_conn()
    try:
        with conn.cursor() as cur:
            if ok:
                cur.execute(
                    """
                    UPDATE radio_program_sessions
                    SET status = 'subtitled', is_downloaded = 1, is_subtitled = 1,
                        srt_filename = %s,
                        filename = IF(filename IS NULL OR filename = '', %s, filename),
                        last_error = NULL
                    WHERE id = %s
                    """,
                    (srt_filename, mp4_filename, sid),
                )
            else:
                cur.execute(
                    """
                    UPDATE radio_program_sessions
                    SET status = 'failed_permanent'
                    WHERE id = %s AND attempts + 1 >= %s
                    """,
                    (sid, MAX_ATTEMPTS),
                )
                cur.execute(
                    """
                    UPDATE radio_program_sessions
                    SET status = 'pending_transcribe', attempts = attempts + 1, last_error = %s
                    WHERE id = %s AND status <> 'failed_permanent'
                    """,
                    (str(error)[:500], sid),
                )
        conn.commit()
    finally:
        conn.close()


def _copy_to_52(files):
    existing = [f for f in files if f and os.path.exists(f)]
    if not existing:
        return
    cmd = ["scp", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "StrictHostKeyChecking=accept-new"]
    if SSH_KEY:
        cmd += ["-i", SSH_KEY]
    cmd += existing + [f"{SSH_TARGET}:{REMOTE_DOWNLOADS}/"]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if res.returncode != 0:
        raise RuntimeError(f"scp to 52 failed: {res.stderr[:300]}")


def process_session(session: dict) -> bool:
    sid, link, attempts = session["id"], session["link"], session["attempts"]
    log.info("session %s: start (attempt %d) %s", sid, attempts + 1, link)

    os.makedirs(WORK_DIR, exist_ok=True)
    media_path = srt_path = None
    try:
        media_path = common.download_media(link, WORK_DIR)
        media_name = os.path.basename(media_path)

        srt_text = common.transcribe_to_srt(media_path)
        srt_name = os.path.splitext(media_name)[0] + ".srt"
        srt_path = os.path.join(WORK_DIR, srt_name)
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_text)
        log.info("session %s: transcribed (%d bytes srt)", sid, os.path.getsize(srt_path))

        _copy_to_52([srt_path] + ([media_path] if KEEP_MP4 else []))
        _finish(sid, True, srt_name, media_name)
        log.info("session %s: DONE", sid)
        return True

    except Exception as exc:  # noqa: BLE001
        log.error("session %s FAILED: %s", sid, exc)
        _finish(sid, False, error=exc)
        for p in (media_path, srt_path):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        return False
    finally:
        if media_path and not KEEP_MP4 and os.path.exists(media_path):
            try:
                os.remove(media_path)
            except OSError:
                pass


def main():
    log.info("worker starting; work_dir=%s batch=%d keep_mp4=%s", WORK_DIR, BATCH_SIZE, KEEP_MP4)
    common.get_model()  # preload model once
    while True:
        try:
            sessions = _next_sessions(BATCH_SIZE)
            for s in sessions:
                process_session(s)
                time.sleep(DELAY_BETWEEN)
            if not sessions:
                time.sleep(IDLE_SLEEP)
        except Exception as exc:  # noqa: BLE001
            log.error("worker loop error (retrying): %s", exc)
            time.sleep(IDLE_SLEEP)


if __name__ == "__main__":
    sys.exit(main())
