import os
import sys
import pathlib
import urllib.parse
import pymysql
from datetime import datetime

# Config from env
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "")
DB_NAME = os.getenv("DB_NAME", "radio")

# GitHub raw for linking subtitle files in repo
GITHUB_USER = os.getenv("GITHUB_USER", "saber13812002")         # e.g. your github username
GITHUB_REPO = os.getenv("GITHUB_REPO", "iranseda-crawler-golang-")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "download-db")

REPO_ROOT = pathlib.Path(__file__).parent.resolve()
DOWNLOADS_DIR = REPO_ROOT / "downloads"  # holds .srt/.txt
DOCS_DIR = REPO_ROOT / "docs"
PROGRAMS_DIR = DOCS_DIR / "programs"

IRAN_SEDA_BASE = "https://radio.iranseda.ir"

def gh_raw_url(relative_path: str) -> str:
    # relative_path like 'downloads/file.srt'
    return f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}/{urllib.parse.quote(relative_path.replace(os.sep, '/'))}"

def ensure_dirs():
    PROGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    # Disable jekyll to allow folders like `_` if needed
    (DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")

def connect_db():
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS,
        database=DB_NAME, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor
    )

def fetch_programs(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, name, url, time, time_description, description, created_at, start, radio, radio_id
            FROM radio_programs
            ORDER BY id ASC
        """)
        return cur.fetchall()

def fetch_sessions_for_program(conn, program_id: int):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, program_id, link, created_at, filename, is_downloaded
            FROM radio_program_sessions
            WHERE program_id = %s
            ORDER BY created_at DESC, id DESC
        """, (program_id,))
        sessions = cur.fetchall()

        # Fetch attached files (if any)
        if not sessions:
            return sessions, {}

        session_ids = tuple(s["id"] for s in sessions)
        placeholders = ",".join(["%s"] * len(session_ids))
        files_by_session = {}
        cur.execute(f"""
            SELECT id, session_id, file_url, filename, is_downloaded
            FROM radio_program_session_files
            WHERE session_id IN ({placeholders})
            ORDER BY id ASC
        """, session_ids)
        for row in cur.fetchall():
            files_by_session.setdefault(row["session_id"], []).append(row)
        return sessions, files_by_session

def find_subtitles_for_session(filename: str):
    # Heuristic: srt/txt with same stem as mp3 filename
    results = []
    if not filename:
        return results
    stem = pathlib.Path(filename).stem
    for ext in (".srt", ".txt"):
        # Original extracted files in downloads/
        candidate = DOWNLOADS_DIR / f"{stem}{ext}"
        if candidate.exists():
            rel = os.path.join("downloads", candidate.name)
            results.append({"type": ext.lstrip("."), "name": candidate.name, "repo_rel": rel, "raw_url": gh_raw_url(rel), "label": "زیرنویس"})
        # Cleaned transcripts in downloads/cleaned/
        cleaned_candidate = DOWNLOADS_DIR / "cleaned" / f"{stem}{ext}"
        if cleaned_candidate.exists():
            rel_cleaned = os.path.join("downloads", "cleaned", cleaned_candidate.name)
            results.append({"type": ext.lstrip("."), "name": cleaned_candidate.name, "repo_rel": rel_cleaned, "raw_url": gh_raw_url(rel_cleaned), "label": "متن کامل"})
    return results

def full_iranseda_url(db_link: str):
    # db_link like '../epgarchivePart/?VALID=TRUE&ch=14&e=.....'
    if not db_link:
        return ""
    if db_link.startswith("http"):
        return db_link
    clean = db_link.replace("..", "").lstrip("/")
    return f"{IRAN_SEDA_BASE}/{clean}"

def html_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def format_time(time_obj):
    if not time_obj:
        return ""
    if isinstance(time_obj, str):
        return time_obj
    if hasattr(time_obj, 'strftime'):
        return time_obj.strftime("%H:%M:%S")
    return str(time_obj)

def render_index(programs):
    items = []
    for p in programs:
        title = html_escape((p.get("name") or "").strip())
        time_info = ""
        if p.get("time"):
            time_info = f" - {format_time(p['time'])}"
        if p.get("time_description"):
            time_info += f" ({html_escape(p['time_description'])})"
        
        items.append(f"""
        <li>
          <a href="programs/{p['id']}.html">{title}</a>{time_info}
        </li>""")
    return f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>فهرست برنامه‌های رادیو ایران‌صدا</title>
<style>
body {{ font-family: 'Tahoma', 'Arial', sans-serif; margin: 24px; background: #f5f5f5; }}
.container {{ max-width: 800px; margin: 0 auto; background: white; padding: 24px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
header {{ margin-bottom: 24px; text-align: center; }}
h1 {{ color: #2c3e50; margin-bottom: 8px; }}
.meta {{ color: #7f8c8d; font-size: 14px; }}
ul {{ list-style: none; padding: 0; }}
ul li {{ margin-bottom: 12px; padding: 12px; background: #f8f9fa; border-radius: 4px; border-right: 3px solid #3498db; }}
ul li a {{ text-decoration: none; color: #2c3e50; font-weight: bold; }}
ul li a:hover {{ color: #e74c3c; }}
</style>
</head>
<body>
<div class="container">
<header>
  <h1>فهرست برنامه‌های رادیو ایران‌صدا</h1>
  <div class="meta">تولید شده در {datetime.now().strftime("%Y-%m-%d %H:%M")} | تعداد برنامه‌ها: {len(programs)}</div>
</header>
<ul>
{''.join(items)}
</ul>
</div>
</body>
</html>"""

def render_program_page(program, sessions, files_by_session):
    title = html_escape((program.get("name") or "").strip())
    
    # Program details section
    details = []
    if program.get("url"):
        details.append(f'<div class="detail-item"><strong>صفحه برنامه:</strong> <a href="{html_escape(program["url"])}" target="_blank" rel="noopener">مشاهده در سایت ایران‌صدا</a></div>')
    
    if program.get("time"):
        details.append(f'<div class="detail-item"><strong>زمان پخش:</strong> {format_time(program["time"])}</div>')
    
    if program.get("time_description"):
        details.append(f'<div class="detail-item"><strong>توضیح زمان:</strong> {html_escape(program["time_description"])}</div>')
    
    if program.get("start"):
        details.append(f'<div class="detail-item"><strong>ساعت شروع:</strong> {format_time(program["start"])}</div>')
    
    if program.get("radio"):
        details.append(f'<div class="detail-item"><strong>رادیو:</strong> {html_escape(program["radio"])}</div>')
    
    if program.get("radio_id"):
        details.append(f'<div class="detail-item"><strong>شناسه رادیو:</strong> {program["radio_id"]}</div>')
    
    if program.get("description"):
        details.append(f'<div class="detail-item"><strong>توضیحات:</strong> <p>{html_escape(program["description"])}</p></div>')
    
    created_at = program.get("created_at")
    if created_at:
        created_str = created_at.strftime("%Y-%m-%d %H:%M") if isinstance(created_at, datetime) else html_escape(str(created_at))
        details.append(f'<div class="detail-item"><strong>تاریخ ایجاد:</strong> {created_str}</div>')

    # Sessions list
    lis = []
    for s in sessions:
        mp3_name = s.get("filename") or ""
        mp3_external = full_iranseda_url(s.get("link") or "")
        subs = find_subtitles_for_session(mp3_name)
        attach = files_by_session.get(s["id"], [])

        # Subtitle links
        subs_html = ""
        if subs:
            links = []
            for sub in subs:
                css = "sub-link" if sub.get("label") == "زیرنویس" else "file-link"
                label_prefix = "زیرنویس:" if sub.get("label") == "زیرنویس" else "متن کامل:" if sub.get("label") == "متن کامل" else "فایل:"
                links.append(f'<span>{label_prefix} <a href="{sub["raw_url"]}" target="_blank" rel="noopener" class="{css}">{html_escape(sub["name"])}</a></span>')
            subs_html = f'<div class="subs"><strong>متن‌ها:</strong> {" | ".join(links)}</div>'

        # Attached files
        attach_html = ""
        if attach:
            links = []
            for f in attach:
                label = html_escape(f.get("filename") or f.get("file_url") or "فایل")
                url = f.get("file_url") or ""
                if url and not url.startswith("http"):
                    url = full_iranseda_url(url)
                links.append(f'<a href="{html_escape(url)}" target="_blank" rel="noopener" class="file-link">{label}</a>')
            attach_html = f'<div class="attachments"><strong>فایل‌های مرتبط:</strong> {" | ".join(links)}</div>'

        created = s.get("created_at")
        created_str = created.strftime("%Y-%m-%d %H:%M") if isinstance(created, datetime) else html_escape(str(created or ""))
        
        downloaded_status = "✅ دانلود شده" if s.get("is_downloaded") else "❌ دانلود نشده"

        lis.append(f"""
        <li class="session-item">
          <div class="session-header">
            <strong>{html_escape(mp3_name) if mp3_name else 'قسمت بدون نام'}</strong>
            <span class="status">{downloaded_status}</span>
          </div>
          <div class="session-meta">
            <span>تاریخ: {created_str}</span>
            <span>شناسه: {s["id"]}</span>
          </div>
          <div class="session-links">
            <div class="mp3-link">
              <strong>MP3 (ایران‌صدا):</strong> 
              <a href="{html_escape(mp3_external)}" target="_blank" rel="noopener" class="mp3-link">{html_escape(mp3_external)}</a>
            </div>
            {subs_html}
            {attach_html}
          </div>
        </li>""")

    return f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>{title}</title>
<style>
body {{ font-family: 'Tahoma', 'Arial', sans-serif; margin: 0; background: #f5f5f5; }}
.container {{ max-width: 1000px; margin: 0 auto; background: white; min-height: 100vh; }}
header {{ background: #2c3e50; color: white; padding: 24px; }}
.breadcrumbs {{ margin-bottom: 16px; }}
.breadcrumbs a {{ color: #3498db; text-decoration: none; }}
.breadcrumbs a:hover {{ color: #e74c3c; }}
h1 {{ margin: 0 0 16px 0; }}
.details {{ background: #ecf0f1; padding: 16px; margin: 16px 0; border-radius: 4px; }}
.detail-item {{ margin-bottom: 8px; }}
.detail-item strong {{ color: #2c3e50; }}
.sessions {{ padding: 24px; }}
.sessions h2 {{ color: #2c3e50; margin-bottom: 20px; }}
.sessions > li {{ margin-bottom: 20px; padding: 16px; background: #f8f9fa; border-radius: 6px; border-right: 4px solid #3498db; }}
.session-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
.status {{ font-size: 12px; padding: 2px 6px; border-radius: 3px; }}
.session-meta {{ color: #7f8c8d; font-size: 12px; margin-bottom: 8px; }}
.session-meta span {{ margin-left: 12px; }}
.session-links {{ margin-top: 8px; }}
.session-links > div {{ margin-bottom: 6px; }}
.mp3-link a {{ color: #e74c3c; font-weight: bold; }}
.sub-link {{ color: #27ae60; }}
.file-link {{ color: #8e44ad; }}
a {{ text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<div class="container">
<header>
<nav class="breadcrumbs"><a href="../index.html">← بازگشت به فهرست برنامه‌ها</a></nav>
<h1>{title}</h1>
</header>

<div class="details">
{''.join(details) if details else '<div>اطلاعات اضافی موجود نیست</div>'}
</div>

<section class="sessions">
  <h2>قسمت‌ها ({len(sessions)} قسمت)</h2>
  <ul>
  {''.join(lis) if lis else '<li>موردی یافت نشد.</li>'}
  </ul>
</section>
</div>
</body>
</html>"""

def generate():
    print("🚀 Starting static site generation...")
    ensure_dirs()
    
    try:
        conn = connect_db()
        print("✅ Connected to database")
        
        programs = fetch_programs(conn)
        print(f"📊 Found {len(programs)} programs")
        
        # Generate index page
        index_html = render_index(programs)
        (DOCS_DIR / "index.html").write_text(index_html, encoding="utf-8")
        print("✅ Generated index.html")
        
        # Generate program pages
        for i, p in enumerate(programs, 1):
            sessions, files_by_session = fetch_sessions_for_program(conn, p["id"])
            html = render_program_page(p, sessions, files_by_session)
            (PROGRAMS_DIR / f"{p['id']}.html").write_text(html, encoding="utf-8")
            print(f"✅ Generated program {i}/{len(programs)}: {p['id']}.html ({len(sessions)} sessions)")
        
        print(f"🎉 Site generation complete! Output: {DOCS_DIR}")
        print(f"📁 Files created:")
        print(f"   - {DOCS_DIR / 'index.html'}")
        print(f"   - {PROGRAMS_DIR}/*.html ({len(programs)} files)")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    if GITHUB_USER == "USERNAME":
        print("⚠️  WARNING: Set GITHUB_USER, GITHUB_REPO, GITHUB_BRANCH env vars for correct raw links.")
        print("   Example: $env:GITHUB_USER='YourUsername'")
    generate()
