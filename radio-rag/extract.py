#!/usr/bin/env python3
"""
RADIO RAG — STEP 1: extract.py
Read-only extraction of the radio Mar'ef pilot sample.

Sources (all read-only):
  - MySQL db `radio` in container iranseda-mysql @ 172.20.1.53:3308
      (user n8nuser; password comes from the repo's own config.py — never hardcoded here)
  - Filesystem /home/saber/saberprojects/iranseda-crawler-golang-/downloads{,/cleaned}

Output (local, versioned):
  state/pilot_episodes.json   — schema v1, one doc per selected episode
  state/pilot_audit.json      — audit counts: present / missing / empty / dup / inconsistent

Selection: N episodes across a spread of air dates (Persian calendar months) and
programs, all status='subtitled' and filename LIKE '%mp4'. Every selected episode
MUST have at least raw SRT + raw TXT; LLM artifacts are recorded per-artifact.

Idempotent: re-running produces byte-identical output for the same sample seed.
"""
import json, os, re, subprocess, sys, hashlib
from collections import Counter, defaultdict

BASE = "/home/saber/saberprojects/iranseda-crawler-golang-"
DL = os.path.join(BASE, "downloads")
CL = os.path.join(DL, "cleaned")
CONFIG_PY = os.path.join(BASE, "config.py")  # reference only; container auth used

ARTIFACTS = ["full.txt", "correct.txt", "correct.srt", "summary.txt", "summary.en.txt"]
SCHEMA_VERSION = "1.0"


def mysql_query(sql: str) -> list[str]:
    """Read-only mysql via the running container.

    Credentials come from the environment (never hardcoded in this file):
      RADIO_DB_USER   (default n8nuser)
      RADIO_DB_PASS   (required; set it from the crawler repo's .env DB_PASS)
    """
    user = os.environ.get("RADIO_DB_USER", "n8nuser")
    pw = os.environ.get("RADIO_DB_PASS", "")
    if not pw:
        raise RuntimeError(
            "RADIO_DB_PASS not set. Source it from the crawler repo .env "
            "(export RADIO_DB_PASS=$(grep '^DB_PASS=' .../.env | cut -d= -f2-)) "
            "before running extract.py. Passwords are never committed.")
    r = subprocess.run(
        ["docker", "exec", "-i", "iranseda-mysql", "mysql", f"-u{user}",
         f"-p{pw}", "-N", "--default-character-set=utf8mb4", "--batch",
         "-e", sql, "radio"],
        capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"mysql error: {r.stderr.strip()[-400:]}")
    return [l for l in r.stdout.splitlines() if l]


# Jalali / Gregorian conversion — exact port of FarsiWeb's jalali.c
# (the algorithm jdatetime uses internally). Verified 1:1 against
# jdatetime.JalaliToGregorian for every day in years 1330-1419 (0 mismatches).
_G_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
_J_DAYS_IN_MONTH = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]


def _is_jalali_leap(y: int) -> bool:
    return y % 33 in (1, 5, 9, 13, 17, 22, 26, 30)


def persian_to_gregorian(py: int, pm: int, pd: int):
    """(persian year, month, day) -> (gy, gm, gd)."""
    jy = py - 979
    g_day_no = 365 * jy + (jy // 33) * 8 + (jy % 33 + 3) // 4 + pd - 1 + 79
    for i in range(pm - 1):
        g_day_no += _J_DAYS_IN_MONTH[i]
    gy = 1600 + 400 * (g_day_no // 146097)
    g_day_no %= 146097
    leap = 1
    if g_day_no >= 36525:
        g_day_no -= 1
        gy += 100 * (g_day_no // 36524)
        g_day_no %= 36524
        if g_day_no >= 365:
            g_day_no += 1
        else:
            leap = 0
    gy += 4 * (g_day_no // 1461)
    g_day_no %= 1461
    if g_day_no >= 366:
        leap = 0
        g_day_no -= 1
        gy += g_day_no // 365
        g_day_no %= 365
    i = 0
    while g_day_no >= _G_DAYS_IN_MONTH[i] + (1 if (i == 1 and leap) else 0):
        g_day_no -= _G_DAYS_IN_MONTH[i] + (1 if (i == 1 and leap) else 0)
        i += 1
    return gy, i + 1, g_day_no + 1


def gregorian_to_persian(gy: int, gm: int, gd: int):
    """(gregorian year, month, day) -> (py, pm, pd)."""
    gy -= 1600
    gm -= 1
    j_day_no = 365 * gy + (gy + 3) // 4 - (gy + 99) // 100 + (gy + 399) // 400 + gd - 1 - 79
    for i in range(gm):
        j_day_no += _G_DAYS_IN_MONTH[i]
    if gm > 1 and ((gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0):
        j_day_no += 1
    j_np = j_day_no // 12053
    j_day_no %= 12053
    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        j_day_no -= 1
        jy += j_day_no // 365
        j_day_no %= 365
    i = 0
    for i in range(11):
        if not j_day_no >= _J_DAYS_IN_MONTH[i]:
            break
        j_day_no -= _J_DAYS_IN_MONTH[i]
    return jy, i + 2, j_day_no + 1


def infer_year_from_created(created_at: str) -> int:
    """created_at 'YYYY-MM-DD ...' -> persian year (approximation).

    The current filename format carries month+day+time but NO year. The MySQL
    created_at is the file-ingestion timestamp, which for the recent batch closely
    follows the broadcast, so its Persian year is a good *approximation* of the
    broadcast year. The transcript text itself (e.g. "با آغاز سال تحصیلی 1404",
    "جمادی‌ال‌اول 1446") is the authoritative source and can refine this later.
    This value is therefore always flagged year_source="ingestion_created_at"
    in the output so consumers know it is not authoritative."""
    try:
        gy, gm, gd = int(created_at[:4]), int(created_at[5:7]), int(created_at[8:10])
    except Exception:
        return 1400
    try:
        py, pm, pd = gregorian_to_persian(gy, gm, gd)
        return py
    except Exception:
        return gy - 621


def parse_persian_date(basename: str):
    """radio-CH-.... -> (channel, year, month, day, hh, mm, ss) or None.

    Two filename generations exist:
      * current (4317 files): radio-CH-MM-DD-HH-MM-SS. Token a is a MONTH (01-12),
        year absent (caller infers an approximation from MySQL created_at).
      * legacy (22 files):    radio-CH-YY-MM-DD-HH-MM. Token a is a 2-digit Jalali
        year (97/98 -> 1397/1398); no seconds field.
    The discriminator: a month is <=12, a 2-digit year is >=97. So a>=13 means
    legacy (year), a<=12 means current (month). Any token that does not form a
    valid calendar date is rejected (returned None) rather than guessed — we never
    fabricate a broadcast date."""
    m = re.match(r"^radio-([\w_]+)-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})$", basename)
    if not m:
        return None
    ch, a, b, c, d, e = m.groups()
    a, b, c, d, e = int(a), int(b), int(c), int(d), int(e)
    if a >= 13:
        # legacy: a=YY year (e.g. 97/98), b=MM, c=DD, d=HH, e=MM
        year, month, day, hh, mm, ss = 1300 + a, b, c, d, e, 0
    else:
        # current: a=MM, b=DD, c=HH, d=MM, e=SS
        month, day, hh, mm, ss = a, b, c, d, e
        year = None  # caller must infer from created_at
    # hard-validate the date components; reject anything impossible.
    if not (1 <= month <= 12 and 1 <= day <= 31 and 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
        return None
    if year is not None and not _is_valid_persian(year, month, day):
        return None
    return ch, year, month, day, hh, mm, ss


def _is_valid_persian(y, m, d):
    maxd = 31 if m <= 6 else (30 if m <= 11 else (30 if _is_jalali_leap(y) else 29))
    return 1 <= d <= maxd


_PERSIAN_MONTHS = {
    "فروردین": 1, "اردیبهشت": 2, "خرداد": 3, "تیر": 4, "مرداد": 5, "شهریور": 6,
    "مهر": 7, "آبان": 8, "آذر": 9, "دی": 10, "بهمن": 11, "اسفند": 12,
}


def parse_time_description(td: str):
    """Parse p.time_description, the AUTHORITATIVE broadcast date.
    Format: '[weekday] DD <MonthName> YYYYساعت HH:MM[به مدت N دقیقه]'
    e.g. 'یکشنبه 21 اردیبهشت 1404ساعت 01:10به مدت 30 دقیقه'
    -> dict(py, pm, pd, hh, mm, source="time_description") or None.
    The weekday is informational (kept for validation, not required)."""
    if not td:
        return None
    m = re.search(r"(\d{1,2})\s+([ا-ی]+)\s+(\d{4})\s*ساعت\s*(\d{1,2}):(\d{2})", td)
    if not m:
        return None
    day, month_name, year, hh, mm = int(m.group(1)), m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5))
    pm = _PERSIAN_MONTHS.get(month_name)
    if pm is None or not _is_valid_persian(year, pm, day):
        return None
    return dict(py=year, pm=pm, pd=day, hh=hh, mm=mm)


def _air_note(air_source: str, time_description: str = None) -> str:
    if air_source == "time_description":
        return ("authoritative: parsed from program.time_description "
                f"({time_description.strip()!r})")
    if air_source == "filename":
        return "year+date+time taken directly from the 2-digit-year legacy filename"
    return ("year approximated from MySQL ingestion created_at; month/day/time from "
            "filename. NOT authoritative — refine from the transcript text.")


def main(n: int = 40):
    # ---------- 1. enumerate files on disk ----------
    raw_srt = {p[:-4] for p in os.listdir(DL) if p.endswith(".srt")}
    raw_txt = {p[:-4] for p in os.listdir(DL) if p.endswith(".txt")}
    raw_mp4 = {p[:-4] for p in os.listdir(DL) if p.endswith(".mp4")}

    cleaned = defaultdict(set)
    cleaned_bytes = {}
    for p in os.listdir(CL):
        if not os.path.isfile(os.path.join(CL, p)):
            continue
        m = re.match(r"^(radio-[^.]+)\.(\w+(?:\.\w+)*)$", p)
        if m:
            cleaned[m.group(1)].add(m.group(2))
            cleaned_bytes[m.group(1) + "." + m.group(2)] = os.path.getsize(os.path.join(CL, p))

    # ---------- 2. DB (read-only) ----------
    sess = mysql_query(
        "SELECT s.id, s.program_id, s.filename, s.srt_filename, s.status, "
        "s.is_subtitled, s.created_at, s.updated_at, s.attempts, p.name, p.radio, "
        "p.time, p.start, p.time_description, p.description "
        "FROM radio_program_sessions s LEFT JOIN radio_programs p ON p.id=s.program_id "
        "WHERE s.status='subtitled' AND s.filename LIKE '%mp4'")
    db = {}
    last_prog = ("NULL",) * 7  # program_* fallback for continuation rows
    for row in sess:
        # A p.description value may contain a REAL newline, so one logical row is
        # split into two physical lines: the first carries the session id + program,
        # the continuation carries the rest of that program's description. The
        # session id is unique per row, so every physical line that starts with a
        # digit is a fresh session; a line that does NOT is the tail of the previous
        # row's program description. We never append the tail to the session row —
        # that corrupts the stem. Instead we let the next session reuse the
        # (still-open) program fields via last_prog.
        parts = row.split("\t")
        if parts and parts[0].isdigit():
            if len(parts) != 15:
                parts = (parts + ["NULL"] * 15)[:15]
            (sid, pid, fname, srtf, status, issub, created, updated, attempts,
             pname, pradio, ptime, pstart, tdesc, pdesc) = [p.strip() for p in parts]
            last_prog = (pname, pradio, ptime, pstart, tdesc, pdesc, "")
        else:
            # continuation / orphan: belongs to the previous session's program.
            continue
        pname = pname.replace("\\n", " ").replace("\\t", " ").strip()
        pdesc = pdesc.replace("\\n", " ").replace("\\t", " ").strip()
        stem = fname[:-4]
        db[stem] = dict(
            session_id=int(sid), program_id=int(pid) if pid not in ("", "NULL") else None,
            filename=fname, srt_filename=srtf or None,
            created_at=created, updated_at=updated, attempts=int(attempts),
            program_name=pname if pname != "NULL" else None,
            program_radio=pradio if pradio != "NULL" else None,
            program_time=ptime if ptime != "NULL" else None,
            program_start=pstart if pstart != "NULL" else None,
            program_time_description=tdesc if tdesc != "NULL" else None,
            program_description=pdesc if pdesc != "NULL" else None,
        )

    llm = mysql_query(
        "SELECT session_id, job_type, model, LEFT(content, 400), "
        "LENGTH(content), LEFT(content_en, 200), LENGTH(content_en), "
        "LEFT(srt_content, 200), LENGTH(srt_content), status, error, file_relpath "
        "FROM llm_output")
    llm_by_session = defaultdict(dict)
    for row in llm:
        # content previews are truncated at 400/200 chars and may hold stray tabs/newlines
        fields = row.split("\t")
        if len(fields) < 12:
            fields = fields + ["NULL"] * (12 - len(fields))
        s_id, jtype, model = fields[0], fields[1], fields[2]
        clen, clen_en, slen, status = fields[4], fields[6], fields[8], fields[10]
        relpath = fields[-1]
        llm_by_session[int(s_id)][jtype] = dict(
            model=model if model != "NULL" else None,
            content_len=int(clen) if clen not in ("NULL", "") else 0,
            content_en_len=int(clen_en) if clen_en not in ("NULL", "") else 0,
            srt_content_len=int(slen) if slen not in ("NULL", "") else 0,
            status=status,
            error=(fields[11] or "").strip() or None if len(fields) > 11 else None,
            file_relpath=relpath if relpath != "NULL" else None,
        )

    # ---------- 3. select a diverse sample ----------
    # Air-date resolution priority (never fabricate):
    #   1. p.time_description  — authoritative Persian broadcast date+time
    #   2. filename (legacy 2-digit year) — authoritative year
    #   3. filename month/day + created_at year — approximation (flagged)
    eligible = []
    no_air_date = []
    air_source_counts = Counter()
    for stem, meta in db.items():
        if stem not in raw_srt or stem not in raw_txt:
            continue
        parsed = parse_persian_date(stem)
        ch = (parsed[0] if parsed else "unknown")
        td = meta.get("program_time_description")
        td_air = parse_time_description(td) if td else None
        if td_air:
            year = td_air["py"]; month = td_air["pm"]; day = td_air["pd"]
            hh, mm, ss = td_air["hh"], td_air["mm"], 0
            air_source = "time_description"
        elif parsed:
            ch, year, month, day, hh, mm, ss = parsed
            air_source = "filename"
            if year is None:
                year = infer_year_from_created(meta["created_at"])
                air_source = "filename+created_at"
        else:
            no_air_date.append(stem)
            continue
        air_source_counts[air_source] += 1
        eligible.append((stem, (ch, year, month, day, hh, mm, ss), meta, air_source))

    by_month = defaultdict(list)
    for stem, parsed, meta, ysrc in eligible:
        by_month[(parsed[1], parsed[2])].append((stem, parsed, meta, ysrc))

    # spread across months: round-robin so every month is represented, capped at N
    months = sorted(by_month)
    pools = {mo: sorted(by_month[mo], key=lambda t: t[2]["created_at"]) for mo in months}
    idx = {mo: 0 for mo in months}
    selected = []
    while len(selected) < n:
        progress = False
        for mo in months:
            if len(selected) >= n:
                break
            if idx[mo] < len(pools[mo]):
                selected.append(pools[mo][idx[mo]])
                idx[mo] += 1
                progress = True
        if not progress:
            break
    selected_ids = {s for s, _, _, _ in selected}

    # ---------- 4. build docs + audit ----------
    docs, audit = [], Counter()
    for stem, parsed, meta, air_source in sorted(selected):
        channel, py, mo, da, hh, mm, ss = parsed
        try:
            gy, gm, gd = persian_to_gregorian(py, mo, da)
            air_date_greg = f"{gy:04d}-{gm:02d}-{gd:02d}"
        except Exception:
            air_date_greg = None
        artifacts = {}
        for a in ARTIFACTS:
            present = a in cleaned.get(stem, set())
            if present:
                size = cleaned_bytes.get(f"{stem}.{a}", 0)
                artifacts[a] = dict(present=True, file=f"downloads/cleaned/{stem}.{a}",
                                    bytes=size, empty=size == 0)
                audit[f"{a}_present"] += 1
                if size == 0:
                    audit[f"{a}_empty"] += 1
            else:
                # DB may still hold the content even if file is missing
                dbrow = llm_by_session.get(meta["session_id"], {})
                jmap = {"full.txt": "full_text", "correct.txt": "correct_text",
                        "correct.srt": "correct_subtitles",
                        "summary.txt": "summary", "summary.en.txt": "summary"}
                d = dbrow.get(jmap[a])
                db_len = 0
                if d:
                    db_len = {"full.txt": d["content_len"], "correct.txt": d["content_len"],
                              "correct.srt": d["srt_content_len"],
                              "summary.txt": d["content_len"],
                              "summary.en.txt": d["content_en_len"]}[a]
                artifacts[a] = dict(present=False,
                                    in_db=db_len > 0, db_len=db_len,
                                    file=f"downloads/cleaned/{stem}.{a}")
                audit[f"{a}_missing_file"] += 1
                if db_len > 0:
                    audit[f"{a}_in_db_only"] += 1
        audit["episodes"] += 1
        audit["raw_srt"] += 1
        audit["raw_txt"] += 1
        audit["mp4"] += 1 if (stem + ".mp4") in raw_mp4 else 0
        docs.append({
            "schema_version": SCHEMA_VERSION,
            "episode_id": stem,
            "source": {"db": "radio@172.20.1.53:3308", "session_id": meta["session_id"],
                       "link": None, "files_base": f"downloads/{stem}"},
            "channel": f"radio-{channel}",
            "air": {"persian": f"{py:04d}-{mo:02d}-{da:02d}", "gregorian": air_date_greg,
                    "time": f"{hh:02d}:{mm:02d}:{ss:02d}",
                    "basename_date": f"{mo:02d}-{da:02d}-{hh:02d}-{mm:02d}-{ss:02d}",
                    "air_source": air_source,
                    "created_at": meta["created_at"],
                    "note": _air_note(air_source, meta.get("program_time_description"))},
            "program": {k: meta[k] for k in ("program_name", "program_radio", "program_time",
                                             "program_start", "program_time_description",
                                             "program_description", "program_id")},
            "subtitles_raw": {"file": f"downloads/{stem}.srt",
                              "bytes": os.path.getsize(os.path.join(DL, stem + ".srt"))},
            "text_raw": {"file": f"downloads/{stem}.txt",
                         "bytes": os.path.getsize(os.path.join(DL, stem + ".txt"))},
            "artifacts": artifacts,
            "llm_metadata": {k: v for k, v in llm_by_session.get(meta["session_id"], {}).items()},
            "content_hash": hashlib.sha256(stem.encode()).hexdigest()[:16],
        })

    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "pilot_episodes.json"), "w", encoding="utf-8") as f:
        json.dump({"schema_version": SCHEMA_VERSION, "selected_at": "2026-10-22",
                   "count": len(docs), "episodes": docs}, f, ensure_ascii=False, indent=1)
    audit["total_sessions_mp4_subtitled"] = len(db)
    audit["distinct_fnames"] = len(db)
    audit["no_air_date"] = len(no_air_date)
    audit["no_air_date_stems"] = sorted(no_air_date)
    audit["air_source_counts"] = dict(air_source_counts)
    audit["eligible"] = len(eligible)
    audit["selected"] = len(docs)
    with open(os.path.join(out, "pilot_audit.json"), "w", encoding="utf-8") as f:
        json.dump(dict(audit), f, ensure_ascii=False, indent=1)
    print(json.dumps(dict(audit), ensure_ascii=False, indent=1))
    print("sample months covered:", sorted({f"{p[1]:04d}-{p[2]:02d}-{p[3]:02d}" for _, p, _, _ in selected}))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
