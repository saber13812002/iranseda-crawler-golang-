#!/usr/bin/env python3
"""
Fetch recent updates from Telegram bot to discover chat IDs (user/group/channel).

Steps:
  1) Set TELEGRAM_BOT_TOKEN in environment.
  2) Send a message to your bot from the target chat (user DM, group, or channel).
  3) Run this script to list recent chat IDs.

Usage:
  TELEGRAM_BOT_TOKEN=xxxx python3 scripts/telegram_get_chat_id.py
"""

import os
import sys
import requests


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN is required")
        sys.exit(1)

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ Error calling getUpdates: {e}")
        sys.exit(1)

    data = resp.json()
    if not data.get("ok"):
        print(f"❌ Telegram returned error: {data}")
        sys.exit(1)

    results = data.get("result", [])
    if not results:
        print("ℹ️ No updates. Send a message to the bot and rerun.")
        return

    print("✅ Recent updates (showing unique chat ids):")
    seen = set()
    for upd in results:
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        chat_type = chat.get("type")
        title = chat.get("title") or chat.get("username") or chat.get("first_name") or "-"
        if chat_id and chat_id not in seen:
            seen.add(chat_id)
            print(f"  - chat_id: {chat_id} | type: {chat_type} | title: {title}")


if __name__ == "__main__":
    main()


