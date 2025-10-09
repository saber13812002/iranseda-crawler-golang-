#!/usr/bin/env python3
"""
Process *.ffmpeg.failed markers in downloads/ and manage DB retry tracking.

Rules:
  - If <file>.ffmpeg.failed exists and no retry record in DB:
      * set session.is_downloaded = 0 (to force retry by downloader)
      * insert retry record with retries_count = 1
      * delete the .ffmpeg.failed marker file
  - If marker exists and retries_count = 1 in DB:
      * DO NOT retry again now
      * update retries_count = 2 (means retried once before and still failing)
      * keep the marker file for visibility

Environment:
  - Uses project DB config via config.py (ENVIRONMENT & DB_* env vars)

Usage:
  python3 scripts/process_failed_ffmpeg.py
"""

import os
import sys
from pathlib import Path
from typing import Optional

import pymysql

from config import get_config


def get_db_conn():
    cfg = get_config()
    return pymysql.connect(
        host=cfg.db_config['host'],
        port=cfg.db_config['port'],
        user=cfg.db_config['user'],
        password=cfg.db_config['password'],
        database=cfg.db_config['database'],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def ensure_retry_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS download_retry_status (
                id INT AUTO_INCREMENT PRIMARY KEY,
                session_id INT NOT NULL UNIQUE,
                retries_count INT NOT NULL DEFAULT 0,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        )
    conn.commit()


def find_session_by_filename(conn, filename: str) -> Optional[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, program_id, filename, is_downloaded FROM radio_program_sessions WHERE filename = %s LIMIT 1",
            (filename,)
        )
        row = cur.fetchone()
        return row


def get_retry_count(conn, session_id: int) -> Optional[int]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT retries_count FROM download_retry_status WHERE session_id = %s",
            (session_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        return int(row["retries_count"])


def set_retry_count(conn, session_id: int, count: int):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO download_retry_status (session_id, retries_count) VALUES (%s, %s)"
            " ON DUPLICATE KEY UPDATE retries_count = VALUES(retries_count)",
            (session_id, count)
        )
    conn.commit()


def force_redownload(conn, session_id: int):
    # Mark as not downloaded so the downloader will retry next run
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE radio_program_sessions SET is_downloaded = 0 WHERE id = %s",
            (session_id,)
        )
    conn.commit()


def main():
    cfg = get_config()
    downloads_dir = cfg.paths['downloads']
    if not downloads_dir.exists():
        print(f"⚠️ downloads directory not found: {downloads_dir}")
        sys.exit(0)

    failed_files = list(downloads_dir.glob("*.ffmpeg.failed"))
    if not failed_files:
        print("ℹ️ No .ffmpeg.failed markers found.")
        return

    conn = get_db_conn()
    try:
        ensure_retry_table(conn)
        processed = 0
        for marker in failed_files:
            base_name = marker.name[:-len('.ffmpeg.failed')]  # original filename

            session = find_session_by_filename(conn, base_name)
            if not session:
                print(f"❓ No session found for {base_name}; skipping")
                continue

            session_id = session['id']
            retry_count = get_retry_count(conn, session_id)

            if retry_count is None:
                # First time: schedule retry and remove marker
                force_redownload(conn, session_id)
                set_retry_count(conn, session_id, 1)
                try:
                    marker.unlink()
                    print(f"🔁 Scheduled retry and removed marker: {marker.name} (session {session_id})")
                except Exception as e:
                    print(f"⚠️ Could not remove marker {marker}: {e}")
                processed += 1
            elif retry_count == 1:
                # Second encounter: do not retry again now, mark as 2
                set_retry_count(conn, session_id, 2)
                print(f"⏭️ Skipped second retry; marked retries_count=2 for session {session_id} ({marker.name})")
                processed += 1
            else:
                print(f"ℹ️ Already at retries_count={retry_count}; no action for session {session_id}")

        print(f"✅ Processed {processed} marker(s).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()


