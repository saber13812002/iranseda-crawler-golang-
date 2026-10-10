"""
iranseda LLM post-processing jobs.

Turns a whisper transcript (.srt) into derived outputs via a chat LLM routed
through the LiteLLM proxy (server 52). Four distinct job types, each its own
phase / job / output file (stored 1:many under downloads/cleaned/ AND in the
llm_output DB table so a new job can be re-run over everything later):

  full_text          strip timestamps (mechanical, no LLM) -> <stem>.full.txt
  summary            bilingual LLM summary (FA + EN)      -> <stem>.summary.txt
                                                            + <stem>.summary.en.txt
  correct_text       LLM-cleaned full text                -> <stem>.correct.txt
  correct_subtitles  LLM-cleaned SRT (keeps timestamps)   -> <stem>.correct.srt

Prompts live in the DB (prompts table) with per-job defaults seeded on first
run. Model auto-discovery reads the proxy's /v1/models.

The summary is bilingual: a single LLM call returns a Persian summary and an
English summary, split into the two `content` / `content_en` DB columns and
two files, so each language is its own first-class field.

Runs as a script on server 53 (dashboard venv). Importable by the dashboard:
    import llm_jobs
    llm_jobs.discover_models(base_url, key)
    llm_jobs.run_batch("summary", model, prompt_text, limit=10)
    llm_jobs.run_over_all_files("summary", model, prompt_text)   # every .srt on disk

CLI:
    python llm_jobs.py ensure-schema
    python llm_jobs.py discover
    python llm_jobs.py run --job summary --limit 10 --model qwen38-nothinking
    python llm_jobs.py run-all --job summary --model qwen38-nothinking
    python llm_jobs.py report --n 3
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime

import pymysql
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.environ.get(
    "IRANSEDA_ROOT", os.path.abspath(os.path.join(BASE_DIR, ".."))
)
DOWNLOADS = os.path.join(PROJECT_ROOT, "downloads")
CLEANED = os.path.join(DOWNLOADS, "cleaned")

# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

def _dashboard_env():
    path = os.path.join(BASE_DIR, "dashboard.env")
    out = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def _llm_cfg():
    env = _dashboard_env()
    return {
        "base_url": (os.environ.get("LITELLM_BASE_URL")
                     or env.get("LITELLM_BASE_URL")
                     or "http://172.20.1.52:4000").rstrip("/"),
        "key": (os.environ.get("LITELLM_MASTER_KEY")
                or env.get("LITELLM_MASTER_KEY") or ""),
    }


def _db_conn():
    env = {}
    ep = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(ep):
        for line in open(ep, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return pymysql.connect(
        host=os.environ.get("DB_HOST") or env.get("DB_HOST") or "127.0.0.1",
        port=int(os.environ.get("DB_PORT") or env.get("DB_PORT") or "3308"),
        user=os.environ.get("DB_USER") or env.get("DB_USER") or "n8nuser",
        password=os.environ.get("DB_PASS") or env.get("DB_PASS") or "",
        database=os.environ.get("DB_NAME") or env.get("DB_NAME") or "radio",
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
    )


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS llm_job (
        id INT AUTO_INCREMENT PRIMARY KEY,
        job_type VARCHAR(32) NOT NULL,
        model VARCHAR(120) NOT NULL,
        prompt_id INT,
        prompt_text MEDIUMTEXT,
        started_at DATETIME NOT NULL,
        finished_at DATETIME,
        total INT DEFAULT 0,
        done INT DEFAULT 0,
        failed INT DEFAULT 0,
        note VARCHAR(255),
        UNIQUE KEY uq (job_type, started_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS prompts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        slug VARCHAR(64) NOT NULL UNIQUE,
        job_type VARCHAR(32) NOT NULL,
        name VARCHAR(120) NOT NULL,
        prompt MEDIUMTEXT NOT NULL,
        is_default TINYINT DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS llm_output (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        session_id INT NOT NULL,
        job_type VARCHAR(32) NOT NULL,
        model VARCHAR(120) NOT NULL,
        prompt_id INT,
        job_id INT,
        content MEDIUMTEXT,
        content_en MEDIUMTEXT,
        srt_content MEDIUMTEXT,
        file_relpath VARCHAR(300),
        started_at DATETIME,
        finished_at DATETIME,
        status VARCHAR(20) NOT NULL DEFAULT 'done',
        error VARCHAR(500),
        input_tokens INT,
        output_tokens INT,
        UNIQUE KEY uq_out (session_id, job_type, model),
        KEY k_job (job_id), KEY k_session (session_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    # Per-episode crop boundary detection (STEP 8). One row per session — the
    # in-slot window found in THIS file's transcript by the rule-based
    # detector, plus a confidence + status for a human to review. Idempotent
    # (UNIQUE on session_id); re-detected every run (no stale cache).
    """
    CREATE TABLE IF NOT EXISTS crop_detection (
        id INT AUTO_INCREMENT PRIMARY KEY,
        session_id INT NOT NULL UNIQUE,
        program_id INT,
        start_sec INT NULL,
        end_sec INT NULL,
        confidence ENUM('high','medium','low') NOT NULL DEFAULT 'low',
        status ENUM('cropped','needs_review','none') NOT NULL DEFAULT 'none',
        evidence MEDIUMTEXT,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    # The pipeline-steps registry. Makes the set of phases data-driven: a new
    # step (input file + model + master prompt -> new per-file field) is a row,
    # and every consumer (engine dispatch, guards, site, labels) reads this
    # table instead of a hard-coded job list. job_type in llm_output == slug.
    """
    CREATE TABLE IF NOT EXISTS pipeline_steps (
        id INT AUTO_INCREMENT PRIMARY KEY,
        slug VARCHAR(48) NOT NULL UNIQUE,
        name VARCHAR(120) NOT NULL,
        input_ref VARCHAR(64) NOT NULL DEFAULT 'srt',
        model VARCHAR(120),
        prompt MEDIUMTEXT,
        output_suffix VARCHAR(64) NOT NULL,
        output_kind VARCHAR(16) NOT NULL DEFAULT 'text',
        is_mechanical TINYINT NOT NULL DEFAULT 0,
        enabled TINYINT NOT NULL DEFAULT 1,
        sort_order INT NOT NULL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    # Monthly backfill queue: program suggestions promoted into the pipeline
    # only when the download+subtitle queue is idle (dashboard/backfill.py).
    """
    CREATE TABLE IF NOT EXISTS backfill_list (
        id INT AUTO_INCREMENT PRIMARY KEY,
        program_id INT,
        label VARCHAR(120),
        month VARCHAR(7),
        status VARCHAR(16) NOT NULL DEFAULT 'queued',
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        promoted_at DATETIME NULL,
        note VARCHAR(255)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]

# One-time column upgrades for tables created before the field was added.
# crop_offset/crop_enabled live on radio_programs (owned by the Go crawler);
# we add them here idempotently so the time-block crop has its config home.
# crop_offset = in-slot start of the program audio (00:00:00 = slot start,
# 00:10:00 = middle of a 30-min slot...); `time` (already present) = duration.
MIGRATIONS = [
    ("llm_output", "content_en", "ALTER TABLE llm_output ADD COLUMN content_en MEDIUMTEXT AFTER content"),
    ("radio_programs", "crop_offset", "ALTER TABLE radio_programs ADD COLUMN crop_offset TIME NULL"),
    ("radio_programs", "crop_enabled",
     "ALTER TABLE radio_programs ADD COLUMN crop_enabled TINYINT NOT NULL DEFAULT 0"),
    # STEP 8: per-episode auto crop switch. When 1, _ensure_program_block uses
    # the per-episode detected window (crop_detection) for HIGH-confidence
    # sessions; otherwise it falls back to the fixed offset (if enabled) else
    # the full transcript. Defaults 0 so the existing fixed-offset mode is
    # unchanged.
    ("radio_programs", "crop_auto",
     "ALTER TABLE radio_programs ADD COLUMN crop_auto TINYINT NOT NULL DEFAULT 0"),
]

# One-time index drops. The original llm_job schema had UNIQUE KEY uq
# (job_type, started_at), which collides when parallel shards insert a job row
# in the same second — it's not a real invariant, so drop it.
DROP_INDEXES = [
    ("llm_job", "uq", "ALTER TABLE llm_job DROP INDEX uq"),
]


def _ensure_schema_once(cur):
    for ddl in SCHEMA:
        cur.execute(ddl)
    for table, col, ddl in MIGRATIONS:
        cur.execute(
            "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s",
            (table, col))
        if not cur.fetchone()["c"]:
            cur.execute(ddl)
    for table, idx, ddl in DROP_INDEXES:
        cur.execute(
            "SELECT COUNT(*) AS c FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND INDEX_NAME=%s",
            (table, idx))
        if cur.fetchone()["c"]:
            cur.execute(ddl)
    # seed default prompts
    for key, (job, name, prompt) in DEFAULT_PROMPTS.items():
        cur.execute(
            "INSERT IGNORE INTO prompts (slug, job_type, name, prompt, is_default) "
            "VALUES (%s, %s, %s, %s, 1)",
            (key, job, name, prompt),
        )
    # keep the summary prompt in sync when the default wording changes
    cur.execute(
        "UPDATE prompts SET name=%s, prompt=%s WHERE job_type='summary' AND is_default=1",
        (DEFAULT_PROMPTS["summary"][1], DEFAULT_PROMPTS["summary"][2]))
    # seed the pipeline-steps registry (create-only by slug; the admin may edit
    # a step's model/prompt/enabled afterwards and it won't be clobbered here).
    for (slug, name, input_ref, model, prompt, suffix, kind, mech, order) in DEFAULT_STEPS:
        cur.execute(
            "INSERT IGNORE INTO pipeline_steps "
            "(slug,name,input_ref,model,prompt,output_suffix,output_kind,is_mechanical,sort_order) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (slug, name, input_ref, model, prompt, suffix, kind, mech, order))


def ensure_schema(conn=None, retries=5):
    """Idempotent schema/seed setup. Retries on deadlock: several parallel
    shards may call this at startup, and concurrent DDL + the prompt UPDATE
    can deadlock (MySQL 1213)."""
    own = conn is None
    conn = conn or _db_conn()
    try:
        for attempt in range(retries):
            try:
                with conn.cursor() as cur:
                    _ensure_schema_once(cur)
                conn.commit()
                break
            except Exception:  # noqa: BLE001 — only deadlock retried below
                conn.rollback()
                if attempt == retries - 1:
                    raise
                time.sleep(0.5 * (attempt + 1))
    finally:
        if own:
            conn.close()


DEFAULT_PROMPTS = {
    # key: (job_type, name, master_prompt)
    "summary": (
        "summary", "خلاصه‌نویسی دوزبانه (فارسی + انگلیسی)",
        "تو یک ویراستار خبریِ دوزبانه (فارسی / انگلیسی) هستی. متن زیر پیاده‌سازیِ "
        "صوتیِ یک برنامه‌ی رادیوییِ فارسی است (ممکن است خطای شنیداری داشته باشد). "
        "یک خلاصه‌ی فشرده و روان (۵ تا ۸ جمله) بنویس که مهم‌ترین نکات و نتیجه‌ی بحث "
        "را می‌رساند. خروجی را دقیقاً در دو بخشِ زیر و همین ترتیب بده و هیچ چیز "
        "دیگه‌ای (عنوان، بولت، توضیح) اضافه نکن؛ هر بخش فقط متن خودِ خلاصه است:\n"
        "خلاصه‌ی فارسی:\n<خلاصه‌ی کامل به فارسی>\n"
        "English Summary:\n<the same summary written in fluent English>"
    ),
    "correct_text": (
        "correct_text", "تصحیح متن کامل",
        "تو یک ویراستار و اصلاح‌گر متونِ فارسیِ تخصصی هستی. متن زیر از "
        "پیاده‌سازیِ صوتی (whisper) است و ممکن است اشتباهات شنیداری/تایپی و "
        "آوانگاریِ نادرست داشته باشد. متن را کاملاً اصلاح کن: آوانگاری "
        "درستِ کلمات را برگردان، املای صحیح را رعایت کن، ویرایش جمله‌بندی "
        "روان را انجام بده و از نام‌ها/عنوان‌های درستی استفاده کن. بدون تغییر "
        "محتوا و بدون حذف اطلاعات. فقط متنِ نهاییِ اصلاح‌شده را برگردان؛ "
        "توضیح، توضیحِ تغییرات، بولت یا شماره نیآور."
    ),
    "correct_subtitles": (
        "correct_subtitles", "تصحیح زیرنویس",
        "تو یک ویراستارِ فارسیِ تخصصی هستی. در ادامه بلوک‌های یک زیرنویس (SRT) "
        "آمده است؛ هر بلوک یک شماره، یک تایم‌کد و متن دارد. فقط متنِ هر بلوک را "
        "اصلاح کن (آوانگاری، املا، ویرایش‌کردن)؛ شماره و تایم‌کد را دست نزن. "
        "خروجی را دقیقاً به همان ترتیب و به تعداد همان بلوک‌ها بده؛ هر بلوک را "
        "در یک خط بنویس و بین متنِ بلوک‌ها فقط علامت جداکننده ' ||| ' بگذار. "
        "هیچ توضیح یا اضافاتی اضافه نکن."
    ),
    "correct_text_v2": (
        "correct_text_v2", "تصحیح پرتاب‌ای (پنجره + همپوشانی)",
        "تو یک ویراستارِ فارسیِ تخصصی هستی که فقط خطاهای شنیداریِ یک پیاده‌سازی "
        "صوتی (whisper) را اصلاح می‌کند. ورودی در هر فراخوانی یک پنجرهٔ کوچک است "
        "که سه بخش دارد: [پیش‌زمینه]، [بلوک‌های هدف]، [پس‌زمینه]. دو بخشِ "
        "پیش/پس‌زمینه نسخهٔ اصلیِ ASR را برای درکِ معنایِ بلوک‌های هدف می‌دهند و "
        "باید بی‌دست‌برخورد بمانند؛ فقط متنِ بلوک‌های هدف را اصلاح می‌کنی. "
        "قوانینِ سخت (به هیچ وجه شکسته نشوند):\n"
        "۱) خلاصه‌نویسی ممنوع — محتوا را فشرده، کم یا زیاد نکن؛ هر بلوک هدف دقیقاً "
        "یک بلوک خروجیِ هم‌معادل دارد.\n"
        "۲) اگر از درستِ بودنِ یک کلمه مطمئن نیستی، حدسِ قطعیت‌نازده نزن: یا همانِ "
        "ASR را نگه‌دار، یا معنادارترین و امن‌ترین خوانش را انتخاب کن. (اصلِ "
        "نگهداشتِ متنِ اصلیِ مطمئن بر یک اصلاحِ ریسکی اولویت دارد.)\n"
        "۳) شماره و زمان‌کد و ترتیب را دست نزن.\n"
        "خروجی: فقط متنِ اصلاح‌شدهٔ بلوک‌های هدف، به همان ترتیب، هر بلوک در یک "
        "خط و بین آن‌ها فقط جداکنندهٔ ' ||| '. هیچ توضیح، شماره یا زمان‌کد اضافه "
        "نکن."
    ),
}

JOB_TYPES = ["full_text", "summary", "correct_text", "correct_subtitles"]

# primary output file suffix per job (used for idempotency + the site)
_JOB_SUFFIX = {
    "full_text": ".full.txt",
    "summary": ".summary.txt",
    "correct_text": ".correct.txt",
    "correct_subtitles": ".correct.srt",
    "correct_text_v2": ".correct.v2.srt",
}

# The seed rows for the pipeline_steps registry. Every existing job is a row so
# the engine stays backward-compatible; `program_block` is the NEW mechanical
# crop step (produces the program-only SRT/text, the "new field"). Adding a new
# phase from the admin = a new row here (or via the API) — no code change.
#   input_ref: srt | full_text | program_srt | program_text | step:<slug>
#   output_kind: text | bilingual | srt | program (crop)
DEFAULT_STEPS = [
    # slug, name, input_ref, model, prompt, output_suffix, output_kind, mechanical, order
    ("full_text", "متن کامل (حذف تایم‌کد)", "full_text", None, None,
     ".full.txt", "text", 1, 10),
    ("summary", "خلاصه‌نویسی دوزبانه (فارسی + انگلیسی)", "program_text",
     "qwen38-nothinking", None, ".summary.txt", "bilingual", 0, 20),
    ("correct_text", "تصحیح متن کامل", "program_text", "qwen38-nothinking", None,
     ".correct.txt", "text", 0, 30),
    ("correct_subtitles", "تصحیح زیرنویس (SRT)", "program_srt",
     "qwen38-nothinking", None, ".correct.srt", "srt", 0, 40),
    ("correct_text_v2", "تصحیح پرتاب‌ای (پنجره + همپوشانی)", "srt",
     "qwen38-nothinking", None, ".correct.v2.srt", "windowed-correct", 0, 45),
    ("program_block", "برش بلاک زمانی برنامه", "srt", None, None,
     ".program.srt", "program", 1, 5),
]


def discover_models(base_url=None, key=None, timeout=20):
    cfg = _llm_cfg()
    base_url = (base_url or cfg["base_url"]).rstrip("/")
    key = key or cfg["key"]
    try:
        r = requests.get(base_url + "/v1/models",
                         headers={"Authorization": f"Bearer {key}"}, timeout=timeout)
        r.raise_for_status()
        data = r.json().get("data", [])
        models = [{"id": m.get("id"), "mode": m.get("mode", "?")} for m in data]
        return {"ok": True, "models": models,
                "chat": [m["id"] for m in models if m.get("mode") == "chat"]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def call_llm(model, system, user, base_url=None, key=None,
             max_tokens=2048, temperature=0.2, timeout=180):
    cfg = _llm_cfg()
    url = (base_url or cfg["base_url"]).rstrip("/") + "/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    r = requests.post(url, json=payload,
                      headers={"Authorization": f"Bearer {key or cfg['key']}"},
                      timeout=timeout)
    r.raise_for_status()
    d = r.json()
    choice = d.get("choices", [{}])[0]
    content = (choice.get("message", {}) or {}).get("content", "") or ""
    usage = d.get("usage", {}) or {}
    return content.strip(), usage.get("prompt_tokens"), usage.get("completion_tokens")


# ---------------------------------------------------------------------------
# text helpers
# ---------------------------------------------------------------------------

def srt_parse(content):
    """Parse SRT text -> (full_text, blocks). blocks = [(num, ts, [text_lines])]."""
    blocks = []
    for raw in (content or "").strip().split("\n\n"):
        lines = [l for l in raw.split("\n") if l.strip() != ""]
        if len(lines) >= 2 and "-->" in lines[1]:
            blocks.append((lines[0].strip(), lines[1].strip(), [l for l in lines[2:]]))
    full = " ".join(" ".join(b[2]).strip() for b in blocks).strip()
    return full, blocks


def srt_to_text(srt_path):
    """Return (full_text, blocks) for an SRT file on disk."""
    if not srt_path or not os.path.exists(srt_path):
        return "", []
    content = open(srt_path, encoding="utf-8", errors="replace").read()
    return srt_parse(content)


def read_txt(text_path):
    if text_path and os.path.exists(text_path):
        return open(text_path, encoding="utf-8", errors="replace").read().strip()
    return ""


def load_session_input(session):
    """Return (full_text, srt_text, blocks, srt_path)."""
    stem = os.path.splitext(session.get("filename") or "")[0]
    if not stem:
        return "", "", [], ""
    srt_path = os.path.join(DOWNLOADS, stem + ".srt")
    txt_path = os.path.join(DOWNLOADS, stem + ".txt")
    srt_text = open(srt_path, encoding="utf-8", errors="replace").read() if os.path.exists(srt_path) else ""
    full = read_txt(txt_path)
    blocks = []
    if srt_text:
        full_from_srt, blocks = srt_to_text(srt_path)
        if not full:
            full = full_from_srt
    return full, srt_text, blocks, srt_path


def _clean_llm_text(content):
    """Strip markdown fences, leading labels/bullets the model sometimes adds."""
    c = content.strip()
    c = re.sub(r"^```[a-zA-Z]*\n?", "", c)
    c = re.sub(r"\n?```$", "", c)
    c = re.sub(r"^(?:متن[ :]|خلاصه[ :]|پاسخ[ :]|نتیجه[ :])\s*", "", c)
    lines = [l for l in c.split("\n") if l.strip() != ""]
    return "\n".join(lines).strip()


def _strip_label(text):
    """Drop leading label header line(s) the model may add (e.g. 'خلاصه‌ی
    فارسی:' or 'English Summary:'). A leading line counts as a label only if
    it's short AND ends in a separator (colon/dash) — real body sentences end
    in a period, so they are never stripped. Robust to ZWNJ variants."""
    lines = (text or "").strip().split("\n")
    i = 0
    while i < len(lines):
        l = lines[i].strip()
        if not l:
            i += 1
            continue
        ends_sep = l.rstrip() and l.rstrip()[-1] in ":،:：-–—"
        if len(l) < 48 and ends_sep:
            i += 1
        else:
            break
    return "\n".join(lines[i:]).strip()


def split_summary_bilingual(content):
    """Split a bilingual model summary into (persian, english).

    The model is asked to emit two labeled blocks:
        خلاصه‌ی فارسی:\n<fa>
        English Summary:\n<en>
    We split on the English marker and strip each block's own label line.
    If no English marker is found, the whole text is treated as Persian and
    the English side is left empty (caller may fall back)."""
    c = (content or "").strip()
    c = re.sub(r"^```[a-zA-Z]*\n?", "", c)
    c = re.sub(r"\n?```$", "", c)
    m = re.search(r"(?im)^\s*English\s*Summary\s*[:\-–—]\s*", c)
    if not m:
        m = re.search(r"(?im)^\s*(?:English|EN)\s*[:\-–—]\s*", c)
    if m:
        fa = c[:m.start()]
        en = c[m.end():]
    else:
        fa, en = c, ""
    fa = _strip_label(fa)
    en = _strip_label(en)
    return fa.strip(), en.strip()


def extract_corrected_texts(out, n_expected):
    """Extract corrected text entries (in order) from the model's subtitle
    output, robust to response shape: the model may return a clean multi-block
    SRT, bare texts joined by '|||', or full blocks (number\\ntimestamp\\ntext)
    joined by '|||'. We only want the text, in original order."""
    if "|||" in out:
        texts = []
        for c in [x.strip() for x in out.split("|||") if x.strip()]:
            cl = [l for l in c.split("\n") if l.strip() != ""]
            if cl and re.fullmatch(r"\d+", cl[0].strip()):
                cl = cl[1:]
            if cl and "-->" in cl[0]:
                cl = cl[1:]
            texts.append(" ".join(l.strip() for l in cl if l.strip() != ""))
        return texts
    # no '|||': try to parse as a proper multi-block SRT
    _full, blk = srt_parse(out)
    if len(blk) >= max(1, int(n_expected * 0.5)):
        return [" ".join(b[2]).strip() for b in blk]
    return [out.strip()] if out.strip() else []


def build_srt(blocks, corrected_lines):
    """Rebuild SRT from original timestamps + corrected text lines (by index)."""
    out = []
    n = min(len(blocks), len(corrected_lines))
    for i in range(len(blocks)):
        idx, ts, _ = blocks[i]
        text = corrected_lines[i].strip() if i < n else " ".join(blocks[i][2]).strip()
        out.append(f"{idx}\n{ts}\n{text}")
    return "\n\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# STEP 9B — windowed ASR correction (correct_text_v2)
# ---------------------------------------------------------------------------

# Sliding-window params. Each window sends a small target region (TARGET blocks)
# plus CTX context blocks on each side so the model has local meaning but only
# corrects the target blocks. Original timestamps are preserved verbatim (only
# text changes), so search still jumps to the exact second. TARGET/CTX are
# midpoints of the user's "6-10 blocks" / "2-3 overlap" ranges.
CTV2_TARGET = 8   # blocks corrected per window (spec: 6-10)
CTV2_CTX = 3      # context blocks before & after (spec: 2-3)


def _ctv2_windows(n):
    """Yield (t0, t1, cb, ca) covering every block 0..n-1. t1 exclusive. No target
    block is in two windows (each block is corrected exactly once); context blocks
    overlap between adjacent windows to give the model local meaning."""
    i = 0
    while i < n:
        t0 = i
        t1 = min(i + CTV2_TARGET, n)
        cb = max(0, t0 - CTV2_CTX)
        ca = min(n, t1 + CTV2_CTX)
        yield t0, t1, cb, ca
        i = t1  # advance by target (no target overlap -> no double-apply)


def _ctv2_block(k, blocks):
    idx, ts, lines = blocks[k]
    return f"{idx}\n{ts}\n" + " ".join(x.strip() for x in lines)


def _ctv2_window_prompt(cb, ca, t0, t1, blocks):
    """Build the user message for one window: [context before] / [target] /
    [context after]. Context is labeled read-only; the model only returns the
    corrected target blocks (joined by ' ||| ')."""
    before = "\n\n".join(_ctv2_block(k, blocks[k]) for k in range(cb, t0))
    target = "\n\n".join(_ctv2_block(k, blocks[k]) for k in range(t0, t1))
    after = "\n\n".join(_ctv2_block(k, blocks[k]) for k in range(t1, ca))
    m = t1 - t0
    return (
        f"=== [پیش‌زمینه — فقط برای درکِ معنا، دست نزن] ===\n{before or '(—)'}\n\n"
        f"=== [بلوک‌های هدف — {m} بلوک؛ فقط این‌ها را اصلاح کن] ===\n{target}\n\n"
        f"=== [پس‌زمینه — فقط برای درکِ معنا، دست نزن] ===\n{after or '(—)'}\n\n"
        f"حالا فقط متنِ {m} بلوکِ هدف (به همین ترتیب) را بنویس؛ هر بلوک در یک خط "
        "و بین آن‌ها جداکنندهٔ ' ||| ' بگذار. شماره/زمان‌کد یا توضیح اضافه نکن."
    )


def windowed_correct(srt_text, model, prompt_text, base_url=None, key=None,
                     log=print):
    """STEP 9B: correct an SRT in small windows with context. Returns
    (new_srt_text, stats). The original SRT is only READ; timestamps are preserved
    verbatim. Each block's text comes from the single window that targets it.
    stats carries per-file QA data: windows, llm_calls, changed-block count,
    change_rate, and a list of {idx, orig, fixed} snippets for human review."""
    _full, blocks = srt_parse(srt_text)
    n = len(blocks)
    if not n:
        return srt_text, {"ok": False, "error": "no srt blocks", "blocks": 0}
    corrected = [" ".join(b[2]).strip() for b in blocks]  # original-text baseline
    windows = llm_calls = changed = 0
    snippets = []
    for (t0, t1, cb, ca) in _ctv2_windows(n):
        windows += 1
        m = t1 - t0
        user = _ctv2_window_prompt(cb, ca, t0, t1, blocks)
        try:
            out, _pt, _ot = call_llm(model, prompt_text, user, base_url, key,
                                     max_tokens=1500)
        except Exception as e:  # noqa: BLE001
            log(f"    [v2] window {blocks[t0][0]}..{blocks[t1-1][0]} LLM error: "
                f"{str(e)[:120]} (keeping original for this window)")
            continue
        llm_calls += 1
        texts = extract_corrected_texts(out, m)
        if not texts:
            continue
        for j in range(m):
            gi = t0 + j
            cand = (texts[j].strip() if j < len(texts) else corrected[gi])
            if cand and cand != corrected[gi]:
                changed += 1
                if len(snippets) < 80:
                    snippets.append({"idx": blocks[gi][0],
                                     "orig": corrected[gi], "fixed": cand})
            if cand:
                corrected[gi] = cand
    new_srt = build_srt(blocks, corrected)
    return new_srt, {"ok": True, "blocks": n, "windows": windows,
                     "llm_calls": llm_calls, "changed": changed,
                     "change_rate": (changed / n) if n else 0.0,
                     "snippets": snippets}


def _count_runall_workers():
    """Count OUR OWN live background `llm_jobs.py run-all` procs (the 24h/boost
    backlog burn), read from /proc. These are not interactive users — the stop
    rule must exclude them so the cap measures *external interactive* load only
    (mirrors boost.py's `our_workers`). Returns int >= 0."""
    try:
        import glob
        n = 0
        for p in glob.glob("/proc/[0-9]*/cmdline"):
            try:
                with open(p, "rb") as fh:
                    cl = fh.read().decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                continue
            if "llm_jobs.py" in cl and "run-all" in cl:
                n += 1
        return n
    except Exception:  # noqa: BLE001
        return 0


def model_stop_check(our_workers=0, cap=5):
    """STEP 9B pre-batch guard: the user's rule — do NOT call the model when more
    than `cap` interactive requests are on it. Reuses boost's live Prometheus
    load. Returns (allowed: bool, reason: str); on any uncertainty we do NOT call."""
    try:
        import boost
        load = boost.read_load({"guard": {}})
        if not load.get("ok"):
            return False, f"prometheus unreachable ({load.get('error')}) — not calling model"
        ext = max(0, int(load.get("vllm_running", 0) + load.get("sglang_running", 0)
                          - our_workers))
        if ext > cap:
            return False, f"NOT using model: {ext} interactive requests > cap {cap}"
        return True, f"ok ({ext} interactive requests <= cap {cap})"
    except Exception as e:  # noqa: BLE001
        return False, f"stop-check error ({str(e)[:100]}) — not calling model"


# ---------------------------------------------------------------------------
# pipeline-step registry (data-driven phases) + time-block crop
# ---------------------------------------------------------------------------

def _step_row_by_slug(conn, slug):
    """Return the pipeline_steps row for a slug, or None (short-lived conn)."""
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM pipeline_steps WHERE slug=%s", (slug,))
            return cur.fetchone()
    except Exception:  # noqa: BLE001
        return None


def _steps_by_slug(conn):
    """{slug: row} for all pipeline_steps (for resolving chained inputs)."""
    out = {}
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM pipeline_steps")
            for r in cur.fetchall():
                out[r["slug"]] = r
    except Exception:  # noqa: BLE001
        pass
    return out


def srt_mid_seconds(ts):
    """Mid-point (seconds) of an SRT timestamp 'HH:MM:SS,mmm --> HH:MM:SS,mmm'.
    SRT uses a COMMA for the millisecond separator, so normalize it to a dot
    before float() (a bare float('08,759') raises ValueError -> None)."""
    try:
        a, b = ts.split("-->")
        def _sec(t):
            h, m, s = t.strip().split(":")
            return int(h) * 3600 + int(m) * 60 + float(s.replace(",", "."))
        return (_sec(a) + _sec(b)) / 2.0
    except Exception:  # noqa: BLE001
        return None


def _time_value_to_seconds(v):
    """A MySQL TIME / 'HH:MM:SS' / timedelta-ish -> seconds (int), or None."""
    if v is None:
        return None
    if isinstance(v, int):
        return v
    s = str(v)
    parts = s.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return int(parts[0])
    except Exception:  # noqa: BLE001
        return None


def crop_program(srt_text, offset_sec, dur_sec):
    """Keep only the SRT blocks whose mid-point falls in [offset, offset+dur]
    (the program's block within its ~30-min slot). Renumber 1-based, keep the
    ORIGINAL timestamps. Returns (program_srt_text, program_full_text).

    If the window is empty/None or no blocks match, returns ("", "") so callers
    can fall back to the full transcript."""
    _full, blocks = srt_parse(srt_text or "")
    if not blocks or not dur_sec or dur_sec <= 0:
        return "", ""
    off = max(0, int(offset_sec or 0))
    hi = off + int(dur_sec)
    kept = []
    for _idx, ts, lines in blocks:
        mid = srt_mid_seconds(ts)
        if mid is None:
            continue
        if off <= mid < hi:
            kept.append((ts, lines))
    if not kept:
        return "", ""
    srt_out = []
    full_parts = []
    for i, (ts, lines) in enumerate(kept, 1):
        txt = " ".join(l.strip() for l in lines if l.strip())
        srt_out.append(f"{i}\n{ts}\n{txt}")
        full_parts.append(txt)
    return "\n\n".join(srt_out) + "\n", " ".join(full_parts).strip()


# ---------------------------------------------------------------------------
# STEP 8 — per-episode crop boundary auto-detection (rule-based, NO LLM).
#
# Why per-episode: STEP 7 proved a fixed per-program `crop_offset` is
# structurally unreliable — the target program's in-slot position drifts every
# episode because the ~30-min archive slot opens with variable-length neighbor
# content. So the window is re-detected INDEPENDENTLY in each file's transcript.
#
# The rules are strict and deterministic. A program only gets cropped when its
# boundary is HIGH confidence (both start AND end anchored on real marker lines
# in THIS file, and the resulting window is a plausible length for the program).
# Everything else is NEEDS_REVIEW (no crop, full-transcript fallback, reason +
# markers stored for a human).
# ---------------------------------------------------------------------------
CROP_SLOT_DEFAULT_SEC = 1800  # assume a ~30-min slot unless the file is longer

# Clean program-START cue. Whisper garbles names, but this phrase is a strong,
# program-specific "we are starting this program now" announcement. From the
# STEP-8.1 census this is RARE (1/12 P28, 0/12 P14, 0/11 P12) — that rarity is
# exactly what keeps false starts low; we do NOT use the (mid-program-repeated)
# program-name phrase alone as a start.
_START_PAT = re.compile(r"شروع برامه|شروع برنامه|شروع برامه‌|شروع برنامه‌")
# Program-END cue ("end of the program"). Generic, so it can also fire on a
# neighbor's outro — the plausibility window below is what rejects those.
_END_PAT = re.compile(r"پایان برامه|پایان برنامه|به پایان|خاتمه برامه|خاتمه برنامه")


def _norm_text(t):
    """Normalize for marker matching: strip ZWNJ, collapse whitespace."""
    return re.sub(r"\s+", " ", (t or "").replace("‌", "")).strip()


def detect_boundary(srt_text, program_name=None, program_dur_sec=None,
                    slot_sec=CROP_SLOT_DEFAULT_SEC):
    """Rule-based, per-episode crop boundary detection on ONE SRT transcript.

    Returns a dict:
      {
        "start_sec": int|None, "end_sec": int|None,
        "confidence": "high"|"medium"|"low",
        "status": "cropped"|"needs_review",
        "markers_found": [ {"side","ts","text"}, ... ],   # the actual lines matched
        "evidence": {"reason","start","end","window_sec","dur_sec","..."},
        "window_sec": int|None,
      }

    Confidence (strict, documented in docs/prompts/008):
      HIGH   — BOTH start and end anchored on real marker lines in this file,
               AND window length within [0.7*dur, min(1.2*dur, slot)].
      MEDIUM — exactly ONE side marker-anchored, the other derived from dur
               (e.g. start = end - dur). Do NOT crop; report only.
      LOW    — no usable markers, or window implausible, or no DB duration.
    When in doubt -> LOW (NEEDS_REVIEW).
    """
    _full, blocks = srt_parse(srt_text or "")
    if not blocks:
        return {"start_sec": None, "end_sec": None, "confidence": "low",
                "status": "needs_review", "markers_found": [],
                "evidence": {"reason": "empty srt", "dur_sec": program_dur_sec},
                "window_sec": None}
    dur = int(program_dur_sec) if program_dur_sec else 0
    dur_ok = dur > 0
    lo = int(0.7 * dur) if dur_ok else 0
    hi = min(int(1.2 * dur), int(slot_sec)) if dur_ok else 0

    # mid-point seconds + normalized text per block
    rows = []
    for _idx, ts, lines in blocks:
        mid = srt_mid_seconds(ts)
        if mid is None:
            continue
        rows.append((mid, ts, _norm_text(" ".join(l.strip() for l in lines))))

    start_cands = [(m, ts, t) for (m, ts, t) in rows if _START_PAT.search(t)]
    end_cands = [(m, ts, t) for (m, ts, t) in rows if _END_PAT.search(t)]
    markers = []
    for (m, ts, t) in start_cands:
        markers.append({"side": "start", "ts": _ts_label(ts), "text": t[:120]})
    for (m, ts, t) in end_cands:
        markers.append({"side": "end", "ts": _ts_label(ts), "text": t[:120]})

    start_sec = min(m for (m, _ts, _t) in start_cands) if start_cands else None
    ev = {"dur_sec": dur, "start_cands": len(start_cands), "end_cands": len(end_cands),
          "lo": lo, "hi": hi}

    # --- end selection given a start: prefer a plausible window closest to dur ---
    end_sec = None
    if end_cands:
        e_all = sorted(m for (m, _ts, _t) in end_cands)
        if start_sec is not None:
            plausible = [e for e in e_all if e > start_sec and lo <= (e - start_sec) <= hi]
            if plausible:
                end_sec = min(plausible, key=lambda e: abs((e - start_sec) - dur))
            else:
                # no plausible end after start: keep the latest as evidence, LOW
                end_sec = max(e_all)
        else:
            end_sec = max(e_all)

    window = (end_sec - start_sec) if (start_sec is not None and end_sec is not None) else None
    window = int(window) if window is not None else None

    if start_sec is not None and end_sec is not None:
        if dur_ok and lo <= window <= hi:
            conf = "high"
            reason = (f"start@{start_sec}s + end@{end_sec}s both marker-anchored; "
                      f"window {window}s in [{lo},{hi}]s (dur {dur}s)")
        elif dur_ok:
            conf = "low"
            reason = (f"start@{start_sec}s + end@{end_sec}s anchored but window "
                      f"{window}s outside [{lo},{hi}]s (dur {dur}s) — implausible")
        else:
            conf = "low"
            reason = "start+end anchored but no DB duration to validate the window"
    elif start_sec is not None or end_sec is not None:
        # Exactly one side is marker-anchored; derive the other from the program
        # duration. MEDIUM only if the derived position is within the slot —
        # otherwise the "anchor" was implausible (e.g. a spurious neighbor outro
        # that, minus dur, would put the start before the slot began) -> LOW.
        conf = "medium"
        derived_ok = True
        if start_sec is not None and end_sec is None and dur_ok:
            end_sec = start_sec + dur
            reason = "start marker-anchored, end derived = start+dur"
        elif end_sec is not None and start_sec is None and dur_ok:
            start_sec = end_sec - dur
            reason = "end marker-anchored, start derived = end-dur"
        else:
            conf = "low"
            reason = "one side anchored but no DB duration to derive the other"
            derived_ok = False
        if derived_ok and not (0 <= (start_sec or 0) < slot_sec and 0 <= (end_sec or 0) <= slot_sec):
            conf = "low"
            reason += " — derived position outside the slot (implausible)"
            start_sec = None
            end_sec = None
        window = (end_sec - start_sec) if (start_sec is not None and end_sec is not None) else None
    else:
        conf = "low"
        reason = "no start/end markers found in this transcript"

    ev.update({"reason": reason, "start": start_sec, "end": end_sec,
               "window_sec": window,
               "name_in_text": bool(program_name and
                                    any(program_name.replace("‌", "") in t for (_m, _ts, t) in rows))})
    return {"start_sec": start_sec, "end_sec": end_sec, "confidence": conf,
            "status": "cropped" if conf == "high" else "needs_review",
            "markers_found": markers, "evidence": ev, "window_sec": window}


def _ts_label(ts):
    """'HH:MM:SS,mmm --> HH:MM:SS,mmm' -> 'HH:MM:SS' (mid, for display)."""
    m = srt_mid_seconds(ts)
    if m is None:
        return "???:???:??"
    m = int(m)
    return f"{m//3600:02d}:{m%3600//60:02d}:{m%60:02d}"


def _program_window_for(conn, stem, session):
    """Resolve a session's crop window from its program row.

    Returns (offset_sec, dur_sec, enabled, auto, name). Uses session['program_id']
    when present (DB path), else looks the stem up. `time`=duration,
    `crop_offset`=in-slot start, `crop_enabled`=fixed-offset switch,
    `crop_auto`=per-episode detection switch, name=program name (for detection)."""
    try:
        pid = session.get("program_id")
        if not pid:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT program_id FROM radio_program_sessions WHERE id=%s",
                    (session.get("id"),))
                r = cur.fetchone()
                pid = r["program_id"] if r else None
        if not pid:
            return 0, 0, False, False, ""
        with conn.cursor() as cur:
            cur.execute("SELECT `time`, crop_offset, crop_enabled, crop_auto, name "
                        "FROM radio_programs WHERE id=%s", (pid,))
            p = cur.fetchone()
        if not p:
            return 0, 0, False, False, ""
        off = _time_value_to_seconds(p.get("crop_offset")) or 0
        dur = _time_value_to_seconds(p.get("time")) or 0
        enabled = bool(p.get("crop_enabled"))
        auto = bool(p.get("crop_auto"))
        name = (p.get("name") or "").strip()
        return off, dur, enabled, auto, name
    except Exception:  # noqa: BLE001
        return 0, 0, False, False, ""


def _load_detection(conn, session_id):
    """Read a session's stored crop_detection row (or None)."""
    if not conn or not session_id:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM crop_detection WHERE session_id=%s", (session_id,))
            return cur.fetchone()
    except Exception:  # noqa: BLE001
        return None


def _store_detection(conn, session_id, program_id, res):
    """Upsert a session's crop_detection row (idempotent)."""
    if not conn or not session_id:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO crop_detection "
                "(session_id, program_id, start_sec, end_sec, confidence, status, evidence) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE program_id=VALUES(program_id), "
                "start_sec=VALUES(start_sec), end_sec=VALUES(end_sec), "
                "confidence=VALUES(confidence), status=VALUES(status), "
                "evidence=VALUES(evidence)",
                (session_id, program_id, res["start_sec"], res["end_sec"],
                 res["confidence"], res["status"], json.dumps(res["evidence"], ensure_ascii=False)))
        conn.commit()
    except Exception as e:  # noqa: BLE001
        print(f"[detect] store failed sid={session_id}: {e}", file=sys.stderr)


def _ensure_program_block(conn, session, stem):
    """Resolve (and, when cropping, refresh) <stem>.program.srt / .program.txt
    for this session's crop window and return them. Re-runnable: re-crops every
    time crop is active, so changing offset/duration takes effect on the next
    run (no stale file is ever served).

    Two modes (STEP 8):
      * auto (crop_auto=1): re-detect the boundary in THIS file (rule-based, no
        LLM). If HIGH confidence -> crop to that per-episode window. Otherwise
        (MEDIUM/LOW) -> full-transcript fallback (NEEDS_REVIEW). The detection
        (window + confidence + markers) is stored in crop_detection for review.
      * fixed (crop_enabled=1, auto off): crop to the stored fixed offset+dur.

    The original <stem>.srt is only ever READ, never written.

    Returns (program_srt, program_full, crop_active)."""
    sid = session.get("id")
    p_srt_path = os.path.join(CLEANED, stem + ".program.srt")
    p_txt_path = os.path.join(CLEANED, stem + ".program.txt")
    if not conn:
        full, srt_text, _blocks, _ = load_session_input(session)
        return srt_text, full, False
    off, dur, enabled, auto, name = _program_window_for(conn, stem, session)
    orig_path = os.path.join(DOWNLOADS, stem + ".srt")
    if auto and dur > 0 and os.path.exists(orig_path):
        # per-episode detection (re-detected every run; no stale cache)
        srt_text = open(orig_path, encoding="utf-8", errors="replace").read()
        res = detect_boundary(srt_text, program_name=name, program_dur_sec=dur)
        _store_detection(conn, sid, session.get("program_id") or
                         _program_id_for(conn, session), res)
        if res["confidence"] == "high" and res["start_sec"] is not None:
            p_srt, p_full = crop_program(srt_text, res["start_sec"],
                                         max(1, (res["end_sec"] or 0) - res["start_sec"]))
            if p_srt:
                os.makedirs(CLEANED, exist_ok=True)
                _write(p_srt_path, p_srt)
                _write(p_txt_path, p_full)
                return p_srt, p_full, True
    if enabled and dur > 0 and not auto:
        # legacy fixed-offset crop (unchanged behavior)
        srt_text = ""
        if os.path.exists(orig_path):
            srt_text = open(orig_path, encoding="utf-8", errors="replace").read()
        p_srt, p_full = crop_program(srt_text, off, dur)
        if p_srt:
            os.makedirs(CLEANED, exist_ok=True)
            _write(p_srt_path, p_srt)
            _write(p_txt_path, p_full)
            return p_srt, p_full, True
    # not crop_active (or empty/low-confidence) -> full (original) transcript
    full, srt_text, _blocks, _ = load_session_input(session)
    return srt_text, full, False


def _program_id_for(conn, session):
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT program_id FROM radio_program_sessions WHERE id=%s",
                        (session.get("id"),))
            r = cur.fetchone()
            return r["program_id"] if r else None
    except Exception:  # noqa: BLE001
        return None


def _resolve_step_input(conn, session, stem, input_ref, steps_by_slug):
    """Resolve a step's input (input_ref) -> (text, srt).
    srt | full_text | program_srt | program_text | step:<slug>."""
    if input_ref == "srt":
        full, srt_text, _b, _ = load_session_input(session)
        return full, srt_text
    if input_ref == "full_text":
        full, _srt, _b, _ = load_session_input(session)
        return full, ""
    if input_ref in ("program_srt", "program_text"):
        p_srt, p_full, _a = _ensure_program_block(conn, session, stem)
        if input_ref == "program_srt":
            return p_full, p_srt
        return p_full, ""
    if input_ref.startswith("step:"):
        other = steps_by_slug.get(input_ref[5:])
        if other and other.get("output_suffix"):
            p = os.path.join(CLEANED, stem + other["output_suffix"])
            if os.path.exists(p):
                return read_txt(p), ""
        # fall back to the program/full transcript if the chained output is absent
        p_srt, p_full, _a = _ensure_program_block(conn, session, stem)
        return p_full, ""
    # unknown -> full transcript
    full, srt_text, _b, _ = load_session_input(session)
    return full, srt_text


def known_step_slugs(conn=None):
    """Valid step slugs from the registry, with a static fallback so a missing
    table/row can never crash a running shard."""
    fallback = set(JOB_TYPES) | {s[0] for s in DEFAULT_STEPS}
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT slug FROM pipeline_steps")
            slugs = {r["slug"] for r in cur.fetchall()}
        if slugs:
            return slugs | fallback
    except Exception:  # noqa: BLE001
        pass
    return fallback


# ---------------------------------------------------------------------------
# STEP 8 — detection dry-run / census
# ---------------------------------------------------------------------------

def _stem_of(session):
    return os.path.splitext(session.get("filename") or "")[0]


def _program_duration(conn, pid):
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT `time` FROM radio_programs WHERE id=%s", (pid,))
            r = cur.fetchone()
        return _time_value_to_seconds(r["time"]) if r else 0
    except Exception:  # noqa: BLE001
        return 0


def _md5_file(path):
    try:
        return hashlib.md5(open(path, "rb").read()).hexdigest()
    except Exception:  # noqa: BLE001
        return None


def run_detection(program_id, limit=20, extra_programs=None, conn=None, log=print):
    """STEP 8.4 dry-run: detect boundaries for up to `limit` episodes (padded
    from `extra_programs` if the main program has fewer), report per-episode +
    a distribution table, and assert the ORIGINAL SRT MD5 is unchanged. NO crops
    are written and NO crop_detection rows are stored (pure read)."""
    conn = conn or _db_conn()
    extra = [int(x) for x in (extra_programs or "").split(",") if x.strip()] if extra_programs else []
    pids = [int(program_id)] + extra

    # gather candidate sessions (subtitled, real SRT on disk), main program first
    sessions = []
    with conn.cursor() as cur:
        ph = ",".join(["%s"] * len(pids))
        cur.execute(
            f"SELECT id, filename, program_id FROM radio_program_sessions "
            f"WHERE is_subtitled=1 AND srt_filename IS NOT NULL AND srt_filename<>'' "
            f"AND program_id IN ({ph}) ORDER BY (program_id=%s) DESC, id DESC",
            pids + [int(program_id)])
        for s in cur.fetchall():
            stem = _stem_of(s)
            if not stem or not os.path.exists(os.path.join(DOWNLOADS, stem + ".srt")):
                continue
            sessions.append(s)
            if len(sessions) >= limit:
                break
    if not sessions:
        log("no subtitled sessions with on-disk SRT for the requested program(s)")
        return []

    rows = []
    md5_bad = 0
    for s in sessions:
        stem = _stem_of(s)
        path = os.path.join(DOWNLOADS, stem + ".srt")
        md5_before = _md5_file(path)
        text = open(path, encoding="utf-8", errors="replace").read()
        dur = _program_duration(conn, s["program_id"])
        res = detect_boundary(text, program_name=None, program_dur_sec=dur)
        md5_after = _md5_file(path)
        same = (md5_before == md5_after)
        if not same:
            md5_bad += 1
        rows.append({"session": s["id"], "program": s["program_id"], "stem": stem,
                     "dur": dur, "md5_same": same, **res})
        # per-episode line
        def _d(x):
            return f"{x//60}m" if x >= 60 else f"{x}s"
        log(f"  sid={s['id']:>5} prog={s['program_id']:>2} dur={_d(dur):>4} "
            f"start={_ts_label_s(res['start_sec'])} end={_ts_label_s(res['end_sec'])} "
            f"win={_ms(res['window_sec'])} conf={res['confidence']:>6} st={res['status']}")
        for mk in res["markers_found"]:
            log(f"        [{mk['side']:>5} {mk['ts']}] {mk['text'][:70]}")
    # MD5 gate (STOP if any original changed)
    if md5_bad:
        log(f"!! MD5 MISMATCH on {md5_bad} original SRT(s) — STOP")
    else:
        log(f"MD5: all {len(rows)} original SRT unchanged")

    # distribution table
    wins = sorted(r["window_sec"] for r in rows if r["window_sec"] is not None)
    # only windows that are NOT exactly a derived dur (= dur) — i.e. real
    # anchor-anchored windows — for the "is the window length stable" question
    real_wins = sorted(r["window_sec"] for r in rows
                       if r["window_sec"] is not None
                       and r["evidence"].get("window_sec") != r["evidence"].get("dur_sec"))
    starts = sorted(r["start_sec"] for r in rows if r["start_sec"] is not None)
    def _med(v):
        return v[len(v)//2] if v else None
    log("")
    log("=== DRY-RUN DISTRIBUTION ===")
    log(f"episodes: {len(rows)}")
    confs = [r["confidence"] for r in rows]
    log(f"HIGH={confs.count('high')}  MEDIUM={confs.count('medium')}  "
        f"NEEDS_REVIEW(low)={confs.count('low')}")
    if real_wins:
        log(f"real window-length (anchor-anchored) s: min={_ms(real_wins[0])} "
            f"median={_ms(_med(real_wins))} max={_ms(real_wins[-1])}  (n={len(real_wins)})")
    if wins:
        log(f"all window-length s: min={_ms(wins[0])} median={_ms(_med(wins))} max={_ms(wins[-1])}")
    if starts:
        log(f"start-position s (drift): min={_ms(starts[0])} median={_ms(_med(starts))} "
            f"max={_ms(starts[-1])}  (spread {_ms(starts[-1]-starts[0])})")
    # main-program (pilot) window/dur ratio — the STEP-8.6 relevance
    main_durs = [r["dur"] for r in rows if r["program"] == int(program_id) and r["dur"] >= 60]
    if main_durs and real_wins:
        md = main_durs[0]
        log(f"pilot window/dur ratio: min {real_wins[0]/md:.2f}x "
            f"median {_med(real_wins)/md:.2f}x max {real_wins[-1]/md:.2f}x "
            f"(dur ~{md}s)")
    # per-program tally (the STEP-8.6 gate is per-program: >=10 HIGH on the pilot)
    by_prog = {}
    for r in rows:
        c = by_prog.setdefault(r["program"], {"high": 0, "medium": 0, "low": 0, "n": 0})
        c[r["confidence"]] += 1
        c["n"] += 1
    log("per-program tally (pid: total / high / medium / needs_review):")
    for pid in sorted(by_prog):
        c = by_prog[pid]
        log(f"  prog {pid}: {c['n']} total -> HIGH={c['high']} MED={c['medium']} "
            f"NEEDS_REVIEW={c['low']}")
    # per-episode window/dur ratio (only where both exist)
    ratios = [(r["window_sec"] / r["dur"]) for r in rows
              if r["window_sec"] is not None and r["dur"] and r["window_sec"] != r["dur"]]
    if ratios:
        log(f"window/dur ratio (real windows): min={min(ratios):.2f}x "
            f"median={_med(sorted(ratios)):.2f}x max={max(ratios):.2f}x")
    return rows


def _ms(sec):
    return f"{int(sec)//60:02d}:{int(sec)%60:02d}" if sec is not None else "n/a"


def _ts_label_s(sec):
    return _ms(sec) if sec is not None else "  n/a "


# ---------------------------------------------------------------------------
# per-session processing
# ---------------------------------------------------------------------------

def _process_core(session, job_type, prompt_text, model, conn, base_url=None, key=None,
                  persist=True):
    """Do the LLM/file work for one session (a dict with 'id' (int|None) and
    'filename'). Writes output file(s) under cleaned/; persists to llm_output
    only when `persist` is True AND a real session id is present. Returns a
    dict describing the written output (or an error)."""
    stem = os.path.splitext(session.get("filename") or "")[0]
    if not stem:
        return {"ok": False, "error": "no filename"}
    sid = session.get("id")
    started = datetime.now()
    os.makedirs(CLEANED, exist_ok=True)
    content_en = None
    pt = ot = None

    # Data-driven dispatch: the step row (pipeline_steps) decides the input
    # (input_ref), the operation (output_kind) and the output file (suffix).
    step = _step_row_by_slug(conn, job_type)
    input_ref = (step or {}).get("input_ref", "srt") or "srt"
    output_kind = (step or {}).get("output_kind", "text") or "text"
    suffix = (step or {}).get("output_suffix") or _JOB_SUFFIX.get(job_type, ".out.txt")
    step_model = (step or {}).get("model") or model
    # A brand-new step has no row in `prompts` yet, so run_batch/run_over_all_files
    # pass prompt_text=None. Fall back to the step's own `prompt` (the "master
    # prompt" set in the step editor) so a new step's LLM call has a system prompt.
    if not prompt_text and (step or {}).get("prompt"):
        prompt_text = step["prompt"]
    steps_by_slug = _steps_by_slug(conn) if input_ref.startswith("step:") else {}
    in_text, in_srt = _resolve_step_input(conn, session, stem, input_ref, steps_by_slug)

    file_rel = f"downloads/cleaned/{stem}{suffix}"
    if output_kind == "program":
        # time-block crop -> <stem>.program.srt / .program.txt (a "new field");
        # the original <stem>.srt is left untouched. _ensure_program_block only
        # writes those files when a crop is actually active (HIGH-confidence auto
        # or enabled fixed offset); for NEEDS_REVIEW it returns the full
        # transcript (fallback) WITHOUT materializing a crop file.
        p_srt, p_full, _active = _ensure_program_block(conn, session, stem)
        if _active and p_srt:
            srt_content, content = p_srt, p_full
        else:
            srt_content, content = None, None
    elif output_kind == "bilingual":
        user = in_text
        if not user:
            return {"ok": False, "error": "no transcript text"}
        out, pt, ot = call_llm(step_model, prompt_text, user[:24000], base_url, key,
                               max_tokens=1600)
        fa, en = split_summary_bilingual(out)
        if not fa and not en:
            fa = _clean_llm_text(out)
        content, content_en = fa, (en or None)
        _write(os.path.join(CLEANED, stem + suffix), fa)
        if en:
            _root, _ext = os.path.splitext(stem + suffix)
            _write(os.path.join(CLEANED, _root + ".en" + _ext), en)
        srt_content = None
    elif output_kind == "srt":
        if not in_srt:
            return {"ok": False, "error": "no srt blocks"}
        _f, blocks = srt_parse(in_srt)
        if not blocks:
            return {"ok": False, "error": "no srt blocks"}
        out, pt, ot = call_llm(step_model, prompt_text, in_srt[:24000], base_url, key,
                               max_tokens=4096)
        lines = extract_corrected_texts(out, len(blocks))
        srt_content = build_srt(blocks, lines)
        content = None
        _write(os.path.join(CLEANED, stem + suffix), srt_content)
    elif output_kind == "windowed-correct":
        # STEP 9B: correct_text_v2 — windowed ASR correction with context.
        # input_ref is `srt` so in_srt = the ORIGINAL full .srt. We re-read the
        # original file directly (never a derived field) so the ORIGINAL stays
        # the immutable source of truth. Writes <stem>.correct.v2.srt (+ .txt).
        orig_path = os.path.join(DOWNLOADS, stem + ".srt")
        if not os.path.exists(orig_path):
            orig_path = None
            in_srt = in_srt or ""
        src = (open(orig_path, encoding="utf-8", errors="replace").read()
               if orig_path else in_srt)
        if not src:
            return {"ok": False, "error": "no srt input for windowed-correct"}
        new_srt, stats = windowed_correct(src, step_model, prompt_text,
                                          base_url, key)
        if not stats.get("ok"):
            return {"ok": False, "error": stats.get("error", "windowed-correct")}
        _write(os.path.join(CLEANED, stem + suffix), new_srt)
        srt_content = new_srt
        content = None
    else:  # 'text' — mechanical full_text, or LLM-cleaned text
        if job_type == "full_text":
            content = in_text
        else:
            user = in_text
            if not user:
                return {"ok": False, "error": "no transcript text"}
            out, pt, ot = call_llm(step_model, prompt_text, user[:24000], base_url, key,
                                   max_tokens=4096)
            content = _clean_llm_text(out)
        _write(os.path.join(CLEANED, stem + suffix), content)
        srt_content = None

    if output_kind != "program" and persist and sid is not None and conn is not None:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO llm_output
                  (session_id, job_type, model, content, content_en, srt_content,
                   file_relpath, started_at, finished_at, status, prompt_id,
                   input_tokens, output_tokens)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'done',%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                  content=VALUES(content), content_en=VALUES(content_en),
                  srt_content=VALUES(srt_content), file_relpath=VALUES(file_relpath),
                  finished_at=VALUES(finished_at), status='done', error=NULL,
                  input_tokens=VALUES(input_tokens), output_tokens=VALUES(output_tokens)
                """,
                (sid, job_type, model, content, content_en, srt_content, file_rel,
                 started, datetime.now(),
                 _prompt_id_for(conn, job_type),
                 pt if job_type != "full_text" else None,
                 ot if job_type != "full_text" else None),
            )
        conn.commit()
    return {"ok": True, "file_rel": file_rel, "chars": len(content or srt_content or "")}


def process_session(session, job_type, prompt_text, model, conn, base_url=None, key=None):
    """Back-compat wrapper around _process_core with DB persistence."""
    return _process_core(session, job_type, prompt_text, model, conn,
                         base_url=base_url, key=key, persist=True)


def _prompt_id_for(conn, job_type):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM prompts WHERE job_type=%s AND is_default=1 "
                    "ORDER BY id LIMIT 1", (job_type,))
        r = cur.fetchone()
        return r["id"] if r else None


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ---------------------------------------------------------------------------
# batch runner (DB-driven, by session id)
# ---------------------------------------------------------------------------

def _pick_sessions(conn, limit=None, session_ids=None, only_new=True,
                   program_id=None):
    with conn.cursor() as cur:
        if session_ids:
            ph = ",".join(["%s"] * len(session_ids))
            cur.execute(
                f"SELECT id, filename, program_id FROM radio_program_sessions "
                f"WHERE id IN ({ph}) AND is_subtitled=1 ORDER BY id", session_ids)
        else:
            where = "is_subtitled=1 AND srt_filename IS NOT NULL AND srt_filename <> ''"
            args = []
            if program_id:
                where += " AND program_id=%s"
                args.append(program_id)
            cur.execute(
                f"SELECT id, filename, program_id FROM radio_program_sessions "
                f"WHERE {where} ORDER BY id DESC LIMIT %s", args + [limit or 100])
        return cur.fetchall()


def run_batch(job_type, model=None, prompt_text=None, limit=None,
              session_ids=None, only_new=True, conn=None, log=print,
              program_id=None, force=False):
    own = conn is None
    conn = conn or _db_conn()
    cfg = _llm_cfg()
    model = model or os.environ.get("LLM_MODEL") or "qwen38-nothinking"
    if job_type not in known_step_slugs(conn):
        raise ValueError(f"bad job_type {job_type}")
    if prompt_text is None:
        with conn.cursor() as cur:
            cur.execute("SELECT prompt FROM prompts WHERE job_type=%s AND is_default=1 "
                        "ORDER BY id LIMIT 1", (job_type,))
            r = cur.fetchone()
            prompt_text = r["prompt"] if r else ""

    sessions = _pick_sessions(conn, limit, session_ids, only_new, program_id)
    if only_new and not force and job_type != "full_text" and sessions:
        done_ids = set()
        with conn.cursor() as cur:
            ph = ",".join(["%s"] * len(sessions))
            cur.execute(
                f"SELECT session_id FROM llm_output WHERE job_type=%s AND model=%s "
                f"AND session_id IN ({ph}) AND status='done'", (job_type, model) + tuple(s["id"] for s in sessions))
            done_ids = {r["session_id"] for r in cur.fetchall()}
        sessions = [s for s in sessions if s["id"] not in done_ids]

    job_id = None
    now = datetime.now()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO llm_job (job_type, model, started_at, total) "
            "VALUES (%s,%s,%s,%s)", (job_type, model, now, len(sessions)))
        job_id = cur.lastrowid
    conn.commit()

    done = failed = 0
    for i, s in enumerate(sessions, 1):
        log(f"[{job_type}] {i}/{len(sessions)} session={s['id']} {s.get('filename','')}")
        try:
            res = process_session(s, job_type, prompt_text, model, conn,
                                  base_url=cfg["base_url"], key=cfg["key"])
            if res.get("ok"):
                done += 1
            else:
                failed += 1
                _mark_error(conn, s["id"], job_type, model, job_id, res.get("error"))
        except Exception as e:  # noqa: BLE001
            failed += 1
            _mark_error(conn, s["id"], job_type, model, job_id, str(e)[:400])
            log(f"    error: {str(e)[:200]}")

    with conn.cursor() as cur:
        cur.execute("UPDATE llm_job SET finished_at=%s, done=%s, failed=%s WHERE id=%s",
                    (datetime.now(), done, failed, job_id))
    conn.commit()
    log(f"[{job_type}] done: {done} ok, {failed} failed (job_id={job_id})")
    if own:
        conn.close()
    return {"job_id": job_id, "total": len(sessions), "done": done, "failed": failed}


def _mark_error(conn, sid, job_type, model, job_id, error):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO llm_output (session_id, job_type, model, job_id, started_at, "
            "finished_at, status, error) VALUES (%s,%s,%s,%s,%s,%s,'failed',%s) "
            "ON DUPLICATE KEY UPDATE status='failed', error=VALUES(error)",
            (sid, job_type, model, job_id, datetime.now(), datetime.now(), error))
    conn.commit()


# ---------------------------------------------------------------------------
# STEP 9B — correct_text_v2 QA runner (20-file test, NOT a bulk/boost job)
# ---------------------------------------------------------------------------

def run_v2_qa(model, ids=None, program_id=None, limit=20, conn=None, log=print):
    """Run correct_text_v2 on a small set of sessions (a QA test, never a bulk
    job). Before any LLM spend it checks the model stop rule; if the model is
    busy (>cap interactive users) it ABORTS without calling. For each file it
    writes <stem>.correct.v2.srt, then computes QA: blocks in==out, timestamps
    unchanged, original SRT MD5 unchanged, change rate, and before/after
    snippets. Returns a summary dict."""
    import hashlib
    conn = conn or _db_conn()
    # Exclude OUR OWN background burn (boost `run-all`) from the interactive
    # count — the guard is about *interactive* users, not our 24h backlog burn.
    our = _count_runall_workers()
    allow, reason = model_stop_check(our_workers=our)
    log(f"[v2-qa] model stop check: allowed={allow} (our run-all workers={our}) ({reason})")
    if not allow:
        return {"aborted": True, "reason": reason, "files": []}
    prompt_text = DEFAULT_PROMPTS["correct_text_v2"][2]
    sel = _pick_sessions(conn, limit=limit, session_ids=ids,
                         only_new=False, program_id=program_id)
    files = []
    for s in sel:
        stem = os.path.splitext(s.get("filename") or "")[0]
        if not stem:
            continue
        orig_path = os.path.join(DOWNLOADS, stem + ".srt")
        if not os.path.exists(orig_path):
            continue
        orig_bytes = open(orig_path, "rb").read()
        md5_before = hashlib.md5(orig_bytes).hexdigest()
        orig = orig_bytes.decode("utf-8", "replace")
        _of, oblocks = srt_parse(orig)
        try:
            new_srt, stats = windowed_correct(orig, model, prompt_text, log=log)
        except Exception as e:  # noqa: BLE001
            log(f"  {stem}: ERROR {str(e)[:150]}")
            continue
        if not stats.get("ok"):
            continue
        _wf, wblocks = srt_parse(new_srt)
        # timestamps identical? (index-ordered compare of each block's ts)
        ts_match = (len(oblocks) == len(wblocks) and
                    all(oblocks[i][1] == wblocks[i][1]
                        for i in range(len(oblocks))))
        # block count in==out
        count_match = (len(oblocks) == len(wblocks))
        # original SRT still byte-identical?
        md5_after = hashlib.md5(open(orig_path, "rb").read()).hexdigest()
        md5_same = (md5_before == md5_after)
        out_srt = os.path.join(CLEANED, stem + ".correct.v2.srt")
        os.makedirs(CLEANED, exist_ok=True)
        _write(out_srt, new_srt)
        _write(os.path.join(CLEANED, stem + ".correct.v2.txt"),
               " ".join(" ".join(b[2]).strip() for b in wblocks if b[2]))
        rec = {"stem": stem, "sid": s["id"], "blocks": len(oblocks),
               "count_match": count_match, "ts_match": ts_match,
               "md5_same": md5_same, "windows": stats["windows"],
               "changed": stats["changed"], "change_rate": stats["change_rate"],
               "snippets": stats["snippets"]}
        files.append(rec)
        log(f"  {stem} blocks={len(oblocks)} ts_same={ts_match} "
            f"md5_same={md5_same} changed={stats['changed']} "
            f"(rate {stats['change_rate']:.1%})")
    return {"aborted": False, "stop_reason": reason,
            "files": files,
            "n": len(files),
            "count_match": sum(f["count_match"] for f in files),
            "ts_match": sum(f["ts_match"] for f in files),
            "md5_same": sum(f["md5_same"] for f in files),
            "rates": [f["change_rate"] for f in files]}


# ---------------------------------------------------------------------------
# file-driven runner (over EVERY .srt on disk — "run on all files")
# ---------------------------------------------------------------------------

def _stem_to_session_map(conn):
    """Map every on-disk-usable stem -> a session id (filename + srt_filename)."""
    m = {}
    with conn.cursor() as cur:
        cur.execute("SELECT id, filename, srt_filename FROM radio_program_sessions "
                    "WHERE is_subtitled=1")
        for r in cur.fetchall():
            for k in (os.path.splitext(r["filename"] or "")[0],
                      os.path.splitext(r["srt_filename"] or "")[0]):
                if k and k not in m:
                    m[k] = r["id"]
    return m


def _stem_to_session_rows(conn):
    """Map stem -> {'id':…, 'filename':…, 'program_id':…} for the file-driven
    path, so the crop (and program-aware inputs) can resolve the schedule."""
    m = {}
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, filename, srt_filename, program_id "
                        "FROM radio_program_sessions WHERE is_subtitled=1")
            for r in cur.fetchall():
                for k in (os.path.splitext(r["filename"] or "")[0],
                          os.path.splitext(r["srt_filename"] or "")[0]):
                    if k and k not in m:
                        m[k] = {"id": r["id"],
                                "filename": r["filename"] or (k + ".mp4"),
                                "program_id": r.get("program_id")}
    except Exception:  # noqa: BLE001
        pass
    return m


def run_over_all_files(job_type, model=None, prompt_text=None, limit=None,
                       only_new=True, conn=None, log=print,
                       shard=None, shards=1, program_id=None, force=False):
    """Process EVERY downloads/*.srt on disk for one job (the "run on all files"
    path). Idempotent when only_new: skips a stem whose primary output file
    already exists. Files are written for all stems; the DB row is upserted
    only for stems that map to a real session id.

    For parallel runs, pass shard=i / shards=n to process only stems where
    index % n == i (disjoint subsets, so N workers each take 1/N with no
    file/DB contention)."""
    own = conn is None
    conn = conn or _db_conn()
    cfg = _llm_cfg()
    model = model or os.environ.get("LLM_MODEL") or "qwen38-nothinking"
    if job_type not in known_step_slugs(conn):
        raise ValueError(f"bad job_type {job_type}")
    if prompt_text is None:
        with conn.cursor() as cur:
            cur.execute("SELECT prompt FROM prompts WHERE job_type=%s AND is_default=1 "
                        "ORDER BY id LIMIT 1", (job_type,))
            r = cur.fetchone()
            prompt_text = r["prompt"] if r else ""

    names = sorted(n for n in os.listdir(DOWNLOADS)
                   if n.endswith(".srt") and not n.endswith(".ffmpeg.failed"))
    if shard is not None and shards > 1:
        names = [n for i, n in enumerate(names) if i % shards == shard]
    stems = [os.path.splitext(n)[0] for n in names]
    stem2id = _stem_to_session_map(conn)
    stem2sess = _stem_to_session_rows(conn)
    if program_id:
        stems = [st for st in stems
                 if (stem2sess.get(st) or {}).get("program_id") == program_id]
    if limit:
        stems = stems[:limit]
    step = _step_row_by_slug(conn, job_type)
    suffix = (step or {}).get("output_suffix") or _JOB_SUFFIX.get(job_type, ".out.txt")

    job_id = None
    now = datetime.now()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO llm_job (job_type, model, started_at, total, note) "
            "VALUES (%s,%s,%s,%s,%s)",
            (job_type, model, now, len(stems), "all-files"))
        job_id = cur.lastrowid
    conn.commit()

    done = failed = skipped = unmatched = 0
    for i, stem in enumerate(stems, 1):
        primary = os.path.join(CLEANED, stem + suffix)
        if only_new and not force and os.path.exists(primary):
            skipped += 1
            continue
        sid = stem2id.get(stem)
        if sid is None:
            unmatched += 1
        sess = stem2sess.get(stem) or {"id": sid, "filename": stem + ".mp4",
                                       "program_id": None}
        log(f"[{job_type}] {i}/{len(stems)} {stem} (sid={sid})")
        try:
            res = _process_core(sess, job_type, prompt_text, model, conn,
                                base_url=cfg["base_url"], key=cfg["key"],
                                persist=(sid is not None))
            if res.get("ok"):
                done += 1
            else:
                failed += 1
                if sid is not None:
                    _mark_error(conn, sid, job_type, model, job_id, res.get("error"))
        except Exception as e:  # noqa: BLE001
            failed += 1
            log(f"    error: {str(e)[:200]}")
            if sid is not None:
                try:
                    _mark_error(conn, sid, job_type, model, job_id, str(e)[:400])
                except Exception:  # noqa: BLE001
                    pass

    with conn.cursor() as cur:
        cur.execute("UPDATE llm_job SET finished_at=%s, done=%s, failed=%s WHERE id=%s",
                    (datetime.now(), done, failed, job_id))
    conn.commit()
    log(f"[{job_type}] all-files done: {done} ok, {failed} failed, "
        f"{skipped} skipped(exist), {unmatched} unmatched (job_id={job_id})")
    if own:
        conn.close()
    return {"job_id": job_id, "total": len(stems), "done": done,
            "failed": failed, "skipped": skipped, "unmatched": unmatched}


def backfill_fulltext_from_disk(log=print):
    """Mechanically produce downloads/cleaned/<stem>.full.txt for EVERY
    downloads/*.srt on disk — file-driven (no DB, no LLM). Idempotent: skips a
    .full.txt that already exists. Uses the original .txt if present, else
    strips the SRT timestamps."""
    os.makedirs(CLEANED, exist_ok=True)
    made = skipped = 0
    for name in sorted(os.listdir(DOWNLOADS)):
        if not name.endswith(".srt") or name.endswith(".ffmpeg.failed"):
            continue
        stem = os.path.splitext(name)[0]
        out = os.path.join(CLEANED, stem + ".full.txt")
        if os.path.exists(out):
            skipped += 1
            continue
        txt = read_txt(os.path.join(DOWNLOADS, stem + ".txt"))
        if not txt:
            txt, _ = srt_to_text(os.path.join(DOWNLOADS, name))
        _write(out, txt)
        made += 1
    log(f"fulltext-all: {made} written, {skipped} already present")
    return {"made": made, "skipped": skipped}


# ---------------------------------------------------------------------------
# quality report (before/after, bilingual)
# ---------------------------------------------------------------------------

def _head(text, n=12):
    lines = [l for l in (text or "").split("\n") if l.strip()]
    return "\n".join(lines[:n])


def report(n=1):
    """Return up to n sessions that have summary + correct_text (+ correct_srt),
    with original full text for a before/after comparison. The summary is
    returned as two fields: `summary` (Persian) and `summary_en` (English)."""
    conn = _db_conn()
    out = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT o.session_id, o.model,
                       MAX(CASE WHEN o.job_type='summary'      THEN o.content END) AS summary,
                       MAX(CASE WHEN o.job_type='summary'      THEN o.content_en END) AS summary_en,
                       MAX(CASE WHEN o.job_type='correct_text' THEN o.content END) AS correct
                FROM llm_output o
                GROUP BY o.session_id, o.model
                HAVING summary IS NOT NULL AND correct IS NOT NULL
                LIMIT %s
                """, (n,))
            for row in cur.fetchall():
                sid = row["session_id"]
                with conn.cursor() as c2:
                    c2.execute("SELECT filename FROM radio_program_sessions WHERE id=%s", (sid,))
                    sess = c2.fetchone()
                full, srt_text, blocks, _ = load_session_input(sess or {"filename": ""})
                with conn.cursor() as c3:
                    c3.execute("SELECT srt_content FROM llm_output WHERE session_id=%s "
                               "AND job_type='correct_subtitles' LIMIT 1", (sid,))
                    cr = c3.fetchone()
                out.append({
                    "session_id": sid,
                    "filename": (sess or {}).get("filename"),
                    "model": row["model"],
                    "original": full,
                    "original_head": _head(full),
                    "summary": row["summary"],
                    "summary_en": row["summary_en"],
                    "correct_text": row["correct"],
                    "correct_srt_head": _head((cr or {}).get("srt_content")),
                })
    finally:
        conn.close()
    return out


def report_markdown(items):
    out = []
    for it in items:
        out.append("=" * 72)
        out.append(f"جلسه {it['session_id']}  —  {it['filename']}   (مدل: {it['model']})")
        out.append("=" * 72)
        out.append("\n--- متن کامل (مانند اصلی از whisper) — ۱۲ خط اول ---\n")
        out.append(it["original_head"] or "(ناموجود)")
        out.append("\n\n--- خلاصه (فارسی, LLM) ---\n")
        out.append(it["summary"] or "(ناموجود)")
        out.append("\n\n--- Summary (English, LLM) ---\n")
        out.append(it.get("summary_en") or "(ناموجود)")
        out.append("\n\n--- متن کامل تصحیح‌شده (LLM) — ۱۲ خط اول ---\n")
        out.append(_head(it["correct_text"]) or "(ناموجود)")
        if it.get("correct_srt_head"):
            out.append("\n\n--- زیرنویس تصحیح‌شده (SRT) — ۱۲ خط اول ---\n")
            out.append(it["correct_srt_head"])
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["ensure-schema", "discover", "run", "run-all",
                                    "report", "fulltext-all", "detect"])
    ap.add_argument("--job", default="summary",
                    help="a pipeline_steps slug (full_text, summary, correct_text, "
                         "correct_subtitles, program_block, or a custom step)")
    ap.add_argument("--model", default=os.environ.get("LLM_MODEL", "qwen38-nothinking"))
    ap.add_argument("--prompt", default=None, help="override prompt text (or read from file with @path)")
    ap.add_argument("--limit", type=int, default=-1,
                    help="max items; -1 (default) = 10 for `run`, ALL for `run-all`")
    ap.add_argument("--ids", default=None, help="comma-separated session ids")
    ap.add_argument("--program-id", type=int, default=None,
                    help="restrict to one program (radio_programs.id)")
    ap.add_argument("--all", action="store_true",
                    help="do not skip already-done (force re-run)")
    ap.add_argument("--qa", action="store_true",
                    help="run: for correct_text_v2, do the bounded 20-file QA "
                         "test (model-stop check + per-file QA table + snippets); "
                         "never a bulk/boost job")
    ap.add_argument("--shard", type=int, default=None,
                    help="run-all: this worker's index (0-based) for parallel sharding")
    ap.add_argument("--shards", type=int, default=1,
                    help="run-all: total number of parallel workers")
    ap.add_argument("--n", type=int, default=1, help="report size")
    ap.add_argument("--program", type=int, default=None,
                    help="detect: main program to census (radio_programs.id)")
    ap.add_argument("--extra", default=None,
                    help="detect: comma-separated extra program ids to pad the census")
    ap.add_argument("--dry-run", action="store_true",
                    help="detect: do not write crops / store rows (default for detect)")
    args = ap.parse_args()

    if args.cmd == "ensure-schema":
        ensure_schema()
        print("schema ensured; default prompts seeded")
    elif args.cmd == "discover":
        print(json.dumps(discover_models(), ensure_ascii=False, indent=2))
    elif args.cmd == "run":
        prompt = args.prompt
        if prompt and prompt.startswith("@"):
            prompt = open(prompt[1:], encoding="utf-8").read()
        ensure_schema()
        ids = [int(x) for x in args.ids.split(",")] if args.ids else None
        if args.qa and args.job == "correct_text_v2":
            import json as _json
            res = run_v2_qa(model=args.model, ids=ids,
                            program_id=args.program_id,
                            limit=(args.limit if args.limit and args.limit > 0 else 20))
            print(_json.dumps(res, ensure_ascii=False, indent=2))
            return
        run_batch(args.job, model=args.model, prompt_text=prompt,
                  limit=None if ids else (args.limit if args.limit > 0 else 10),
                  session_ids=ids, only_new=not args.all,
                  program_id=args.program_id, force=args.all)
    elif args.cmd == "run-all":
        prompt = args.prompt
        if prompt and prompt.startswith("@"):
            prompt = open(prompt[1:], encoding="utf-8").read()
        ensure_schema()
        run_over_all_files(args.job, model=args.model, prompt_text=prompt,
                           limit=(args.limit if args.limit > 0 else None),
                           only_new=not args.all, shard=args.shard,
                           shards=args.shards, program_id=args.program_id,
                           force=args.all)
    elif args.cmd == "report":
        items = report(args.n)
        if not items:
            print("(no qualifying sessions yet — run jobs first)")
        print(report_markdown(items))
    elif args.cmd == "fulltext-all":
        backfill_fulltext_from_disk()
    elif args.cmd == "detect":
        ensure_schema()
        if not args.program:
            ap.error("detect needs --program <id> (optionally --extra 14,12 --limit 20)")
        run_detection(args.program,
                      limit=(args.limit if args.limit and args.limit > 0 else 20),
                      extra_programs=args.extra)


if __name__ == "__main__":
    main()
