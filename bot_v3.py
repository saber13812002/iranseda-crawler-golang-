#!/usr/bin/env python3
"""Bale ASR bot v3 — Mission 3, Section 1.

تغییرات نسبت به v2:
  ۱) فارسی‌سازی کامل (پیام شروع، خطاها، وضعیت در‌حال‌پردازش، نتیجه)
  ۲) سقف مدت ویس از ۶۰ ثانیه به ۳۰۰ ثانیه (۵ دقیقه) + اندازه‌گیری واقعی
     (duration میلی‌ثانیهٔ بله + fallback به ffprobe)
  ۳) ارسال فوری پیام «در حال تبدیل» + ویرایش همان پیام با editMessageText
     در پایان (با fallback به پاسخ جداگانه اگر ویرایش ممکن نبود)
  ۴) مهلت‌های (timeout) تطبیقی برای فایل‌های بلندتر
قابلیت قبلی (۱ دقیقه) همچنان باید کار کند.
"""
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

TOKEN = os.environ.get("BALE_BOT_TOKEN", "")
ASR_URL = os.environ.get("ASR_URL", "http://127.0.0.1:9500/v1/audio/transcriptions")
MAX_VOICE_SEC = 300            # ۵ دقیقه (قبلاً ۶۰)
MIN_VOICE_SEC = 1
POLL_TIMEOUT = 25
LOG_FILE = "/home/saber/asr-bot-test/bot.log"

# پیام‌های فارسی
MSG_WELCOME = "🎙️ به ربات تبدیل صدا به متن خوش آمدید.\nپیام صوتی فارسی بفرستید (حداکثر ۵ دقیقه) تا به متن تبدیلش کنم."
MSG_STATUS = "🎙️ فایل صوتی شما دریافت شد. ⏳ در حال تبدیل صدا به متن هستم، لطفاً منتظر بمانید."
MSG_NO_AUDIO = "😕 فایل صوتی شناسایی نشد. لطفاً یک پیام صوتی فارسی ارسال کنید."
MSG_TOO_LONG = (
    "⏱️ این فایل صوتی {} ثانیه است.\n"
    "حداکثر مدت مجاز {} ثانیه (۵ دقیقه) است. لطفاً فایل کوتاه‌تری بفرستید."
)
MSG_TOO_SHORT = "🔇 این فایل صوتی خیلی کوتاه است (کمتر از {} ثانیه). لطفاً یک ویس کامل‌تر بفرستید."
MSG_EMPTY_TEXT = "🤷 متنی قابل تشخیص در این فایل صوتی پیدا نشد."
MSG_ERROR = "⚠️ در پردازش فایل صوتی شما خطایی رخ داد.\nشماره پیگیری: {}"
MSG_FINAL_HEADER = "✅ متن شما:\n\n"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("bale-asr-bot")

API = f"https://tapi.bale.ai/bot{TOKEN}"
FILE_API = f"https://tapi.bale.ai/file/bot{TOKEN}/"


def api(method, payload=None, timeout=60):
    url = f"{API}/{method}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type": "application/json"]
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        result = json.loads(r.read().decode())
    if not result.get("ok"):
        raise RuntimeError(f"Bale API {method} error: {result.get('description')}")
    return result.get("result")


def chat_action(chat_id, action, tid=""):
    """sendChatAction — best-effort؛ هر خطا نادیده گرفته می‌شود."""
    try:
        api("sendChatAction", {"chat_id": str(chat_id), "action": action}, timeout=15)
        trace(tid, "CHAT_ACTION", action=action)
    except Exception as e:
        log.info("[%s] sendChatAction(%s) skipped: %s", tid, action, e)


def trace(trace_id, stage, **kw):
    """Log a trace event with trace_id."""
    extra = " ".join(f"{k}={v}" for k, v in kw.items())
    log.info("[%s] %s %s", trace_id, stage, extra)


def download_bale_file(file_id, max_retries=3, trace_id=""):
    # Bale download URL: https://tapi.bale.ai/file/bot{TOKEN}/{file_id}
    # FILE_API ends with / so this produces the correct path.
    url = FILE_API + file_id
    local = tempfile.mktemp(suffix=".ogg", prefix="bale_voice_")
    path_no_token = f"/file/bot***/{file_id}"

    last_err = None
    for attempt in range(1, max_retries + 1):
        t0 = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "asr-bot-test/1.0"})
            trace(trace_id, "DOWNLOAD_REQUEST", method="GET", path=path_no_token, attempt=attempt)
            with urllib.request.urlopen(req, timeout=120) as r:
                content_type = r.headers.get("Content-Type", "unknown")
                with open(local, "wb") as f:
                    f.write(r.read())
            elapsed = int((time.time() - t0) * 1000)
            actual_size = os.path.getsize(local)
            trace(trace_id, "DOWNLOAD_RESPONSE", status=r.status, ms=elapsed,
                  size=actual_size, content_type=content_type, attempt=attempt)
            return local, actual_size
        except urllib.error.HTTPError as e:
            elapsed = int((time.time() - t0) * 1000)
            trace(trace_id, "DOWNLOAD_RESPONSE", status=e.code, ms=elapsed,
                  error=f"HTTPError: {e.reason}", attempt=attempt)
            last_err = e
            if e.code == 404 and attempt < max_retries:
                wait = 1.5 * attempt
                log.info("[%s] Retrying in %.1fs...", trace_id, wait)
                time.sleep(wait)
            else:
                raise
        except Exception as e:
            elapsed = int((time.time() - t0) * 1000)
            trace(trace_id, "DOWNLOAD_RESPONSE", ms=elapsed,
                  error=f"{type(e).__name__}: {e}", attempt=attempt)
            last_err = e
            if attempt < max_retries:
                wait = 1.5 * attempt
                time.sleep(wait)
            else:
                raise
    raise last_err


def ffprobe_duration(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
            capture_output=True, timeout=30,
        )
        data = json.loads(r.stdout.decode())
        return float(data.get("format", {}).get("duration", 0))
    except Exception as e:
        log.warning("ffprobe failed: %s", e)
        return 0.0


def to_wav16k(src):
    dst = src + ".wav"
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", dst],
        capture_output=True, timeout=180,  # ۵ دقیقه ویدیو/صدا را هم پوشش بده
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr.decode()[:300]}")
    log.info("ffmpeg ok: %s (%d bytes)", dst, os.path.getsize(dst))
    return dst


def asr_transcribe(wav_path, timeout=420):
    boundary = "----Boundary7MA4YWxkTrZu0gW"
    with open(wav_path, "rb") as f:
        file_data = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
        f"Content-Type: audio/wav\r\n\r\n"
    ).encode() + file_data + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="language"\r\n\r\nfa\r\n'
        f"--{boundary}--\r\n"
    ).encode()

    req = urllib.request.Request(
        ASR_URL, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        result = json.loads(r.read().decode())
    return result.get("text", "")


def send_reply(chat_id, text, reply_to=""):
    params = {"chat_id": str(chat_id), "text": text}
    if reply_to:
        params["reply_to_message_id"] = str(reply_to)
    api("sendMessage", params)
    log.info("Reply sent to chat=%s reply_to=%s", chat_id, reply_to)


def send_status(chat_id, msg_id, text, tid=""):
    """پیام وضعیت را بفرست و message_id آن را برگردان (برای ویرایش بعدی).

    اگر sendMessage خطا بدهد، '' برمی‌گرداند تا caller به reply ساده بسند.
    """
    try:
        res = api("sendMessage", {"chat_id": str(chat_id), "text": text}, timeout=30)
        sid = str((res or {}).get("message_id") or (res or {}).get("id") or "")
        trace(tid, "STATUS_SENT", status_msg_id=sid)
        return sid
    except Exception as e:
        log.warning("[%s] failed to send status msg: %s", tid, e)
        return ""


def deliver_result(chat_id, text, status_msg_id, orig_msg_id, tid=""):
    """نتیجه نهایی: ترجیحاً همان پیام «در حال تبدیل» ویرایش می‌شود؛
    در غیر این صورت به‌عنوان پاسخ به ویس اصلی ارسال می‌شود.
    """
    final_text = (MSG_FINAL_HEADER + text) if text else MSG_EMPTY_TEXT

    # ۱) تلاش برای ویرایش پیام وضعیت (اگر ارسال شده بود)
    if status_msg_id:
        try:
            api("editMessageText", {
                "chat_id": str(chat_id),
                "message_id": str(status_msg_id),
                "text": final_text,
            }, timeout=30)
            trace(tid, "RESULT_DELIVERED", mode="edit", status_msg_id=status_msg_id)
            return
        except Exception as e:
            log.warning("[%s] editMessageText failed (%s); falling back to reply", tid, e)
            trace(tid, "EDIT_FAILED", error=str(e))

    # ۲) fallback: پاسخ جداگانه به ویس اصلی
    send_reply(chat_id, final_text, reply_to=orig_msg_id)
    trace(tid, "RESULT_DELIVERED", mode="reply", reply_to=orig_msg_id)


def handle_voice(update):
    tid = uuid.uuid4().hex[:8]
    msg = update.get("message", {})
    chat = msg.get("chat", {})
    chat_id = str(chat.get("id", ""))
    msg_id = str(msg.get("message_id") or msg.get("id") or "")

    trace(tid, "UPDATE_RECEIVED", msg_id=msg_id, chat_id=chat_id,
          update_id=update.get("update_id"))

    voice = msg.get("voice") or {}
    audio = msg.get("audio") or {}
    document = msg.get("document") or {}
    media = voice or audio or document
    file_id = media.get("file_id", "")
    duration_ms = float(media.get("duration") or 0)
    mime = media.get("mime_type", "")
    declared_dur = duration_ms / 1000.0

    trace(tid, "VOICE_PARSED", msg_id=msg_id, file_id_present=bool(file_id),
          duration_ms=duration_ms, mime=mime,
          source="voice" if voice else "audio" if audio else "document")

    if not file_id:
        trace(tid, "ERROR", stage="VOICE_PARSED", detail="no file_id")
        send_reply(chat_id, MSG_NO_AUDIO, reply_to=msg_id)
        return

    # ————— ارسال فوری پیام «در حال پردازش» (قبل از دانلود/پردازش) —————
    status_msg_id = send_status(chat_id, msg_id, MSG_STATUS, tid=tid)
    chat_action(chat_id, "typing", tid)   # best-effort؛ خطایی ایجاد نمی‌کند

    t0 = time.time()
    tmp_files = []
    try:
        local, size = download_bale_file(file_id, trace_id=tid)
        tmp_files.append(local)
        t1 = time.time()
        trace(tid, "DOWNLOAD_DONE", size_bytes=size,
              elapsed_ms=int((t1 - t0) * 1000))

        # اندازه‌گیری واقعی: اگر duration بله صفر بود، ffprobe می‌خواند
        if declared_dur <= 0:
            declared_dur = ffprobe_duration(local)
            trace(tid, "FFPROBE_RESULT", duration_s=round(declared_dur, 2))
        trace(tid, "DURATION_CONFIRMED", duration_s=round(declared_dur, 2),
              from_bale=(declared_dur > 0) if duration_ms > 0 else "ffprobe")

        if declared_dur > MAX_VOICE_SEC:
            trace(tid, "REJECT", reason=f"duration {declared_dur:.0f}s > {MAX_VOICE_SEC}s")
            send_reply(chat_id, MSG_TOO_LONG.format(int(declared_dur), MAX_VOICE_SEC),
                       reply_to=msg_id)
            return
        if 0 < declared_dur < MIN_VOICE_SEC:
            trace(tid, "REJECT", reason=f"duration {declared_dur:.1f}s < {MIN_VOICE_SEC}s")
            send_reply(chat_id, MSG_TOO_SHORT.format(MIN_VOICE_SEC), reply_to=msg_id)
            return

        wav = to_wav16k(local)
        tmp_files.append(wav)
        t2 = time.time()
        trace(tid, "CONVERT_RESULT", wav_bytes=os.path.getsize(wav),
              elapsed_ms=int((t2 - t1) * 1000))

        # مهلت تطبیقی: حداقل ۱۸۰ ثانیه؛ برای فایل ۵ دقیقه ~۴۲۰ ثانیه
        asr_timeout = max(180, int(declared_dur) + 240)
        chat_action(chat_id, "typing", tid)   # نشانهٔ «هنوز فعال»
        text = asr_transcribe(wav, timeout=asr_timeout)
        t3 = time.time()
        trace(tid, "ASR_RESPONSE", text_preview=text[:120] if text else "(empty)",
              asr_timeout_s=asr_timeout, elapsed_ms=int((t3 - t2) * 1000))

        deliver_result(chat_id, text, status_msg_id, msg_id, tid)
        t4 = time.time()
        trace(tid, "SEND_MESSAGE_RESPONSE", total_ms=int((t4 - t0) * 1000),
              asr_ms=int((t3 - t2) * 1000), total_s=round(t4 - t0, 1))

    except Exception as e:
        trace(tid, "ERROR", error=f"{type(e).__name__}: {e}")
        log.exception("[%s] Full traceback for msg_id=%s", tid, msg_id)
        try:
            # اگر پیام وضعیت فرستاده شده، همان را ویرایش کن؛ وگرنه پاسخ بده
            if status_msg_id:
                api("editMessageText", {
                    "chat_id": str(chat_id),
                    "message_id": str(status_msg_id),
                    "text": MSG_ERROR.format(tid),
                }, timeout=30)
                trace(tid, "ERROR_DELIVERED", mode="edit")
            else:
                send_reply(chat_id, MSG_ERROR.format(tid), reply_to=msg_id)
                trace(tid, "ERROR_DELIVERED", mode="reply")
        except Exception:
            log.warning("[%s] could not deliver error message", tid)
    finally:
        for p in tmp_files:
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass


def main():
    log.info("=== Bale ASR bot v3 starting (Mission 3 §1) ===")
    log.info("ASR=%s  max_voice=%ds  min_voice=%ds  POLL_TIMEOUT=%ds",
             ASR_URL, MAX_VOICE_SEC, MIN_VOICE_SEC, POLL_TIMEOUT)
    me = api("getMe")
    log.info("Bot identity: id=%s username=@%s", me.get("id"), me.get("username"))

    offset = 0
    while True:
        try:
            res = api("getUpdates", {"offset": offset, "timeout": POLL_TIMEOUT, "limit": 10})
            updates = res or []
            for upd in updates:
                offset = upd.get("update_id", offset) + 1
                msg = upd.get("message", {})
                text = msg.get("text", "")

                if "voice" in msg or "audio" in msg or "document" in msg:
                    log.info(">>> Inbound MEDIA message: msg_id=%s", msg.get("id"))
                    handle_voice(upd)
                elif text:
                    log.info("text msg id=%s: %s", msg.get("id"), text[:120])
                    send_reply(str(msg.get("chat", {}).get("id", "")),
                               MSG_WELCOME,
                               reply_to=str(msg.get("message_id") or msg.get("id") or ""))
                else:
                    log.info(">>> Inbound non-media, non-text: msg_id=%s keys=%s",
                              msg.get("message_id") or msg.get("id"), list(msg.keys()))
        except Exception as e:
            log.warning("poll loop error: %s: %s", type(e).__name__, e, exc_info=True)
            time.sleep(5)


if __name__ == "__main__":
    if not TOKEN:
        log.error("BALE_BOT_TOKEN not set")
        sys.exit(1)
    main()
