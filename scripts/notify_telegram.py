#!/usr/bin/env python3
"""
Send Telegram notifications for latest downloaded sessions per program within a time window.

Environment variables:
  - TELEGRAM_BOT_TOKEN: Telegram bot token (required)
  - TELEGRAM_CHAT_ID: Target chat id (user, group, or channel). Comma-separated list supported
  - NOTIFY_WINDOW_HOURS: Lookback window in hours (default: 24)
  - ENVIRONMENT, DB_*, GITHUB_*: Reused from project config

Usage (example):
  TELEGRAM_BOT_TOKEN=xxxx TELEGRAM_CHAT_ID=12345 python3 scripts/notify_telegram.py
"""

import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any

import pymysql
import requests

from config import get_config


IRAN_SEDA_BASE = "https://radio.iranseda.ir"
GHPAGES_BASE = f"https://{os.getenv('GITHUB_USER', 'saber13812002')}.github.io/{os.getenv('GITHUB_REPO', 'iranseda-crawler-golang-').strip('/')}/"


def full_iranseda_url(db_link: str) -> str:
    if not db_link:
        return ""
    if db_link.startswith("http"):
        return db_link
    clean = db_link.replace("..", "").lstrip("/")
    return f"{IRAN_SEDA_BASE}/{clean}"


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


def ensure_notifications_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications_sent (
                id INT AUTO_INCREMENT PRIMARY KEY,
                program_id INT NOT NULL,
                session_id INT NOT NULL,
                sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_program_session (program_id, session_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        )
    conn.commit()


def fetch_latest_sessions(conn, since: datetime) -> List[Dict[str, Any]]:
    """
    Return latest downloaded session per program since the given datetime.
    """
    with conn.cursor() as cur:
        # Latest session per program in window and marked downloaded
        cur.execute(
            """
            SELECT rps.id AS session_id,
                   rps.program_id,
                   rps.link,
                   rps.created_at,
                   rps.filename,
                   rp.name AS program_name,
                   rp.url   AS program_url,
                   rp.time_description,
                   rp.time  AS program_time
            FROM radio_program_sessions rps
            JOIN radio_programs rp ON rp.id = rps.program_id
            WHERE rps.is_downloaded = 1
              AND rps.created_at >= %s
            ORDER BY rps.program_id ASC, rps.created_at DESC
            """,
            (since,)
        )
        rows = cur.fetchall()

    # keep only latest per program
    latest_by_program: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        pid = row["program_id"]
        if pid not in latest_by_program:
            latest_by_program[pid] = row
    return list(latest_by_program.values())


def filter_unsent(conn, sessions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not sessions:
        return []
    session_ids = [s["session_id"] for s in sessions]
    placeholders = ",".join(["%s"] * len(session_ids))
    sent = set()
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT session_id FROM notifications_sent WHERE session_id IN ({placeholders})",
            tuple(session_ids),
        )
        for row in cur.fetchall():
            sent.add(row["session_id"])
    return [s for s in sessions if s["session_id"] not in sent]


def fmt_time_value(tval) -> str:
    try:
        return tval.strftime("%H:%M:%S")
    except Exception:
        return str(tval or "")


def make_message(item: Dict[str, Any]) -> str:
    program_id = item["program_id"]
    program_name = (item.get("program_name") or "").strip()
    program_url = item.get("program_url") or ""
    session_time = item.get("created_at")
    filename = item.get("filename") or ""
    time_desc = item.get("time_description") or ""
    sched_time = fmt_time_value(item.get("program_time"))
    iranseda_link = full_iranseda_url(item.get("link") or "")
    program_page = f"{GHPAGES_BASE}programs/{program_id}.html"

    text = (
        f"<b>🔔 Latest Downloaded Episode</b>\n"
        f"📻 <b>Program:</b> {program_name}\n"
        f"🕒 <b>Broadcast time (program):</b> {sched_time} {('(' + time_desc + ')') if time_desc else ''}\n"
        f"📅 <b>Captured at:</b> {session_time.strftime('%Y-%m-%d %H:%M') if hasattr(session_time, 'strftime') else session_time}\n"
        f"🎧 <b>Filename:</b> {filename}\n"
        f"🔗 <b>IranSeda:</b> {iranseda_link}\n"
        f"🌐 <b>Program page:</b> {program_page}\n"
    )
    return text


def send_telegram(bot_token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=20)
        if resp.status_code != 200:
            print(f"❌ Telegram send failed: {resp.status_code} {resp.text}")
            return False
        return True
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False


def mark_sent(conn, items: List[Dict[str, Any]]):
    if not items:
        return
    with conn.cursor() as cur:
        for it in items:
            cur.execute(
                "INSERT IGNORE INTO notifications_sent (program_id, session_id) VALUES (%s, %s)",
                (it["program_id"], it["session_id"]),
            )
    conn.commit()


def main():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_ids_raw = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    window_hours = int(os.getenv("NOTIFY_WINDOW_HOURS", "24"))

    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN is required")
        sys.exit(1)
    if not chat_ids_raw:
        print("❌ TELEGRAM_CHAT_ID is required (single id or comma-separated list)")
        sys.exit(1)

    chat_ids = [cid.strip() for cid in chat_ids_raw.split(",") if cid.strip()]

    since = datetime.now() - timedelta(hours=window_hours)
    conn = get_db_conn()
    try:
        ensure_notifications_table(conn)
        sessions = fetch_latest_sessions(conn, since)
        to_send = filter_unsent(conn, sessions)

        if not to_send:
            print("ℹ️ Nothing new to notify.")
            return

        sent_items = []
        for item in to_send:
            text = make_message(item)
            ok_all = True
            for cid in chat_ids:
                ok = send_telegram(bot_token, cid, text)
                ok_all = ok_all and ok
            if ok_all:
                sent_items.append(item)

        mark_sent(conn, sent_items)
        print(f"✅ Notified {len(sent_items)} items to {len(chat_ids)} chat(s).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()


