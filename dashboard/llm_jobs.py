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
]

# One-time column upgrades for tables created before the field was added.
MIGRATIONS = [
    ("llm_output", "content_en", "ALTER TABLE llm_output ADD COLUMN content_en MEDIUMTEXT AFTER content"),
]

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
}

JOB_TYPES = ["full_text", "summary", "correct_text", "correct_subtitles"]

# primary output file suffix per job (used for idempotency + the site)
_JOB_SUFFIX = {
    "full_text": ".full.txt",
    "summary": ".summary.txt",
    "correct_text": ".correct.txt",
    "correct_subtitles": ".correct.srt",
}


def ensure_schema(conn=None):
    own = conn is None
    conn = conn or _db_conn()
    try:
        with conn.cursor() as cur:
            for ddl in SCHEMA:
                cur.execute(ddl)
            for table, col, ddl in MIGRATIONS:
                cur.execute(
                    "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s",
                    (table, col))
                if not cur.fetchone()["c"]:
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
        conn.commit()
    finally:
        if own:
            conn.close()


# ---------------------------------------------------------------------------
# model discovery
# ---------------------------------------------------------------------------

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

    if job_type == "full_text":
        full, _srt, _blocks, _ = load_session_input(session)
        content = full
        file_rel = f"downloads/cleaned/{stem}.full.txt"
        _write(os.path.join(CLEANED, f"{stem}.full.txt"), content)
        srt_content = None
    elif job_type == "correct_subtitles":
        full, srt_text, blocks, _ = load_session_input(session)
        if not blocks:
            return {"ok": False, "error": "no srt blocks"}
        out, pt, ot = call_llm(model, prompt_text, srt_text[:24000], base_url, key,
                               max_tokens=4096)
        lines = extract_corrected_texts(out, len(blocks))
        srt_content = build_srt(blocks, lines)
        content = None
        file_rel = f"downloads/cleaned/{stem}.correct.srt"
        _write(os.path.join(CLEANED, f"{stem}.correct.srt"), srt_content)
    elif job_type == "summary":
        full, srt_text, blocks, _ = load_session_input(session)
        user = full or srt_text
        if not user:
            return {"ok": False, "error": "no transcript text"}
        out, pt, ot = call_llm(model, prompt_text, user[:24000], base_url, key,
                               max_tokens=1600)
        fa, en = split_summary_bilingual(out)
        if not fa and not en:
            fa = _clean_llm_text(out)
        content = fa
        content_en = en or None
        file_rel = f"downloads/cleaned/{stem}.summary.txt"
        _write(os.path.join(CLEANED, f"{stem}.summary.txt"), fa)
        if en:
            _write(os.path.join(CLEANED, f"{stem}.summary.en.txt"), en)
        srt_content = None
    else:  # correct_text
        full, srt_text, blocks, _ = load_session_input(session)
        user = full or srt_text
        if not user:
            return {"ok": False, "error": "no transcript text"}
        out, pt, ot = call_llm(model, prompt_text, user[:24000], base_url, key,
                               max_tokens=4096)
        content = _clean_llm_text(out)
        file_rel = f"downloads/cleaned/{stem}.correct.txt"
        _write(os.path.join(CLEANED, f"{stem}.correct.txt"), content)
        srt_content = None

    if persist and sid is not None and conn is not None:
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

def _pick_sessions(conn, limit=None, session_ids=None, only_new=True):
    with conn.cursor() as cur:
        if session_ids:
            ph = ",".join(["%s"] * len(session_ids))
            cur.execute(
                f"SELECT id, filename, program_id FROM radio_program_sessions "
                f"WHERE id IN ({ph}) AND is_subtitled=1 ORDER BY id", session_ids)
        else:
            where = "is_subtitled=1 AND srt_filename IS NOT NULL AND srt_filename <> ''"
            cur.execute(
                f"SELECT id, filename, program_id FROM radio_program_sessions "
                f"WHERE {where} ORDER BY id DESC LIMIT %s", (limit or 100,))
        return cur.fetchall()


def run_batch(job_type, model=None, prompt_text=None, limit=None,
              session_ids=None, only_new=True, conn=None, log=print):
    own = conn is None
    conn = conn or _db_conn()
    cfg = _llm_cfg()
    model = model or os.environ.get("LLM_MODEL") or "qwen38-nothinking"
    if job_type not in JOB_TYPES:
        raise ValueError(f"bad job_type {job_type}")
    if prompt_text is None:
        with conn.cursor() as cur:
            cur.execute("SELECT prompt FROM prompts WHERE job_type=%s AND is_default=1 "
                        "ORDER BY id LIMIT 1", (job_type,))
            r = cur.fetchone()
            prompt_text = r["prompt"] if r else ""

    sessions = _pick_sessions(conn, limit, session_ids, only_new)
    if only_new and job_type != "full_text":
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


def run_over_all_files(job_type, model=None, prompt_text=None, limit=None,
                       only_new=True, conn=None, log=print):
    """Process EVERY downloads/*.srt on disk for one job (the "run on all files"
    path). Idempotent when only_new: skips a stem whose primary output file
    already exists. Files are written for all stems; the DB row is upserted
    only for stems that map to a real session id."""
    own = conn is None
    conn = conn or _db_conn()
    cfg = _llm_cfg()
    model = model or os.environ.get("LLM_MODEL") or "qwen38-nothinking"
    if job_type not in JOB_TYPES:
        raise ValueError(f"bad job_type {job_type}")
    if prompt_text is None:
        with conn.cursor() as cur:
            cur.execute("SELECT prompt FROM prompts WHERE job_type=%s AND is_default=1 "
                        "ORDER BY id LIMIT 1", (job_type,))
            r = cur.fetchone()
            prompt_text = r["prompt"] if r else ""

    names = sorted(n for n in os.listdir(DOWNLOADS)
                   if n.endswith(".srt") and not n.endswith(".ffmpeg.failed"))
    stems = [os.path.splitext(n)[0] for n in names]
    total = len(stems)
    if limit:
        stems = stems[:limit]
    stem2id = _stem_to_session_map(conn)
    suffix = _JOB_SUFFIX[job_type]

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
        if only_new and os.path.exists(primary):
            skipped += 1
            continue
        sid = stem2id.get(stem)
        if sid is None:
            unmatched += 1
        log(f"[{job_type}] {i}/{len(stems)} {stem} (sid={sid})")
        sess = {"id": sid, "filename": stem + ".mp4"}
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
                                    "report", "fulltext-all"])
    ap.add_argument("--job", default="summary", choices=JOB_TYPES)
    ap.add_argument("--model", default=os.environ.get("LLM_MODEL", "qwen38-nothinking"))
    ap.add_argument("--prompt", default=None, help="override prompt text (or read from file with @path)")
    ap.add_argument("--limit", type=int, default=-1,
                    help="max items; -1 (default) = 10 for `run`, ALL for `run-all`")
    ap.add_argument("--ids", default=None, help="comma-separated session ids")
    ap.add_argument("--all", action="store_true", help="do not skip already-done")
    ap.add_argument("--n", type=int, default=1, help="report size")
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
        run_batch(args.job, model=args.model, prompt_text=prompt,
                  limit=None if ids else (args.limit if args.limit > 0 else 10),
                  session_ids=ids, only_new=not args.all)
    elif args.cmd == "run-all":
        prompt = args.prompt
        if prompt and prompt.startswith("@"):
            prompt = open(prompt[1:], encoding="utf-8").read()
        ensure_schema()
        run_over_all_files(args.job, model=args.model, prompt_text=prompt,
                           limit=(args.limit if args.limit > 0 else None),
                           only_new=not args.all)
    elif args.cmd == "report":
        items = report(args.n)
        if not items:
            print("(no qualifying sessions yet — run jobs first)")
        print(report_markdown(items))
    elif args.cmd == "fulltext-all":
        backfill_fulltext_from_disk()


if __name__ == "__main__":
    main()
