#!/usr/bin/env python3
"""
Send notifications to Telegram or Bale (Baale) messenger.

This script reads messenger credentials from environment variables and sends messages
to multiple chat IDs. It can be used with n8n or run manually.

Environment variables:
  - MESSENGER_TYPE: "telegram" or "bale" (default: telegram)
  - MESSENGER_BOT_TOKEN: Bot token (required)
  - MESSENGER_CHAT_ID: Target chat id(s), comma-separated (required)
  - ENVIRONMENT, DB_*: Database configuration (from project config)

Usage:
  # Telegram
  MESSENGER_BOT_TOKEN=xxx MESSENGER_CHAT_ID=12345 python3 scripts/notify_messenger.py "Your message"

  # Bale
  MESSENGER_TYPE=bale MESSENGER_BOT_TOKEN=xxx MESSENGER_CHAT_ID=12345 python3 scripts/notify_messenger.py "Your message"
"""

import os
import sys
import requests
from pathlib import Path

# Ensure project root is importable
sys.path.append(str(Path(__file__).resolve().parents[1]))


def send_telegram(bot_token: str, chat_id: str, message: str, parse_mode: str = "HTML") -> bool:
    """Send message via Telegram Bot API"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
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


def send_bale(bot_token: str, chat_id: str, message: str, parse_mode: str = "HTML") -> bool:
    """Send message via Bale (Baale) Bot API"""
    url = f"https://tapi.bale.ai/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=20)
        if resp.status_code != 200:
            print(f"❌ Bale send failed: {resp.status_code} {resp.text}")
            return False
        return True
    except Exception as e:
        print(f"❌ Bale error: {e}")
        return False


def main():
    messenger_type = os.getenv("MESSENGER_TYPE", "telegram").lower()
    bot_token = os.getenv("MESSENGER_BOT_TOKEN", "").strip()
    chat_ids_raw = os.getenv("MESSENGER_CHAT_ID", "").strip()

    if not bot_token:
        print("❌ MESSENGER_BOT_TOKEN is required")
        sys.exit(1)
    if not chat_ids_raw:
        print("❌ MESSENGER_CHAT_ID is required (single id or comma-separated list)")
        sys.exit(1)

    chat_ids = [cid.strip() for cid in chat_ids_raw.split(",") if cid.strip()]

    # Get message from command line argument or stdin
    if len(sys.argv) > 1:
        message = " ".join(sys.argv[1:])
    else:
        message = sys.stdin.read()

    if not message.strip():
        print("❌ No message provided")
        sys.exit(1)

    sent_count = 0
    failed_count = 0

    for chat_id in chat_ids:
        if messenger_type == "telegram":
            ok = send_telegram(bot_token, chat_id, message)
        elif messenger_type == "bale":
            ok = send_bale(bot_token, chat_id, message)
        else:
            print(f"❌ Unknown messenger type: {messenger_type}")
            sys.exit(1)

        if ok:
            sent_count += 1
            print(f"✅ Sent to {messenger_type} chat {chat_id}")
        else:
            failed_count += 1
            print(f"❌ Failed to send to {messenger_type} chat {chat_id}")

    print(f"\n📊 Summary: {sent_count} sent, {failed_count} failed to {len(chat_ids)} chat(s)")
    
    if failed_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

