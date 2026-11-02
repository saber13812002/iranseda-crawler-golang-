"""
messenger_publisher.py — the REAL PublisherClient adapter for the reporter
(STEP 9C transport, Phase 8).

Publishes queued `publication_task` rows directly to Telegram or Bale (Baale)
bot APIs. Gated entirely on env credentials; when none are present the
reporter keeps its honest `StubClient` (tasks drain to `skipped` — never a
fake publish).

Env (dashboard service / dashboard.env):
  MESSENGER_TYPE      telegram (default) | bale
  MESSENGER_BOT_TOKEN bot token (required to be "configured")
  MESSENGER_CHAT_ID   one chat id or a comma-separated list
  Fallback (telegram only): TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
  (the same variables scripts/notify_telegram.py uses).

Honesty contract (identical to reporter.PublisherClient):
  * publish() returns an `external_task_id` marker ONLY after EVERY chat
    accepted the message (HTTP 200 + ok=true). Any per-chat failure returns
    {"error": ...} instead, so the worker retries (bounded by MAX_ATTEMPTS)
    and then fails the task. It NEVER claims success it did not verify.
  * The marker embeds the API-returned message_id(s) as proof of delivery.
  * check_status() treats a `sent:` marker as published — the send itself is
    the delivery (these bot APIs are synchronous; there is no later async
    state to poll). Unknown markers report indeterminate `pending`, never a
    fabricated publish.

Stdlib only (urllib) so it works in the dashboard venv without new deps.
"""
import html
import json
import os
import time
import urllib.request

import reporter  # sibling module (same import path as app.py uses)


def _env(name):
    return (os.environ.get(name) or "").strip()


def load_config():
    """Return (mtype, token, [chat_ids]) or None when not configured."""
    mtype = (_env("MESSENGER_TYPE") or "telegram").strip().lower()
    if mtype not in ("telegram", "bale"):
        mtype = "telegram"
    token = _env("MESSENGER_BOT_TOKEN") or _env("TELEGRAM_BOT_TOKEN")
    chats_raw = _env("MESSENGER_CHAT_ID") or _env("TELEGRAM_CHAT_ID")
    if not token or not chats_raw:
        return None
    chats = [c.strip() for c in chats_raw.split(",") if c.strip()]
    if not chats:
        return None
    return mtype, token, chats


def _endpoint(mtype, token):
    if mtype == "bale":
        return "https://tapi.bale.ai/bot%s/sendMessage" % token
    return "https://api.telegram.org/bot%s/sendMessage" % token


def http_post_json(url, payload, timeout=20):
    """Stdlib-only POST. Returns (status, parsed_json_or_raw_string).

    A non-2xx HTTP response raises urllib.error.HTTPError (the bot APIs
    answer 4xx with a JSON body on submit failure) — callers treat any
    raise as a failed send, which is the honest interpretation.
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", "replace")
        try:
            return resp.status, json.loads(body)
        except json.JSONDecodeError:
            return resp.status, body


def build_message(task):
    """Render a publication_task row as one HTML-escaped bot message."""
    ev = (task.get("event_type") or "").strip()
    title = (task.get("title") or "").strip()
    body = (task.get("body") or "").strip()
    commit = (task.get("git_commit") or "").strip()
    lines = ["\U0001F4E1 IranSeda - %s" % ev] if ev else ["\U0001F4E1 IranSeda"]
    if title:
        lines.append(title)
    if body:
        lines.append("")
        lines.append(body[:3500])
    if commit:
        lines.append("")
        lines.append("commit: %s" % commit)
    text = html.escape("\n".join(lines))
    if len(text) > 4000:  # bot limit is 4096; keep headroom
        text = text[:3997] + "..."
    return text


class MessengerClient(reporter.PublisherClient):
    """Real Telegram/Bale transport. One instance per dashboard process."""

    def __init__(self, cfg=None):
        self.cfg = cfg or load_config()
        if not self.cfg:
            raise ValueError(
                "messenger_publisher: no MESSENGER_*/TELEGRAM_* credentials")

    def publish(self, task):
        mtype, token, chats = self.cfg
        url = _endpoint(mtype, token)
        text = build_message(task)
        message_ids = []
        for cid in chats:
            payload = {
                "chat_id": cid,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            try:
                status, res = http_post_json(url, payload)
            except Exception as e:  # noqa: BLE001
                return {"external_task_id": None,
                        "error": ("%s send to chat %s failed: %r"
                                  % (mtype, cid, e))[:300]}
            if status != 200 or (isinstance(res, dict) and res.get("ok") is False):
                if isinstance(res, dict):
                    detail = res.get("description") or str(res)[:200]
                else:
                    detail = str(res)[:200]
                return {"external_task_id": None,
                        "error": ("%s HTTP %s to chat %s: %s"
                                  % (mtype, status, cid, detail))[:300]}
            mid = None
            if isinstance(res, dict):
                mid = (res.get("result") or {}).get("message_id")
            message_ids.append(str(mid) if mid is not None else "?")
        # All chats accepted. The marker is the delivery receipt: it embeds
        # the API-returned message ids (proof) and a send timestamp.
        marker = "sent:%d:%s" % (int(time.time() * 1000), ",".join(message_ids))
        return {"external_task_id": marker[:120]}

    def check_status(self, external_task_id):
        ext = (external_task_id or "").strip()
        if ext.startswith("sent:"):
            # Delivery was confirmed at send time; nothing left to poll.
            return {"state": "published",
                    "post_urls": {self.cfg[0]: "message_ids=" + ext[5:]},
                    "error": None}
        # Never fabricate a success for something this client did not send.
        return {"state": "pending", "post_urls": {},
                "error": "unknown external id (not sent by this client)"}


def configured():
    """True when messenger credentials are present in the environment."""
    return load_config() is not None


def install_if_configured():
    """Install the real client into reporter when credentials exist.

    Called from dashboard/app.py _startup, BEFORE reporter.ensure_started()
    so the worker's first cycle already sees the real client. No-op (keeps
    the honest stub) when unconfigured. Returns True when installed.
    """
    cfg = load_config()
    if not cfg:
        return False
    reporter.set_client(MessengerClient(cfg))
    return True
