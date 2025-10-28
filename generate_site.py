import os
import sys
import pathlib
import urllib.parse
import pymysql
from datetime import datetime
from config import get_config

# Load configuration based on environment
config = get_config()

# Use config values
DB_HOST = config.db_config['host']
DB_PORT = config.db_config['port']
DB_USER = config.db_config['user']
DB_PASS = config.db_config['password']
DB_NAME = config.db_config['database']

# GitHub configuration
GITHUB_USER = config.github_config['user']
GITHUB_REPO = config.github_config['repo']
GITHUB_BRANCH = config.github_config['branch']

# Paths from config
DOWNLOADS_DIR = config.paths['downloads']
DOCS_DIR = config.paths['docs']
PROGRAMS_DIR = config.paths['programs']

IRAN_SEDA_BASE = "https://radio.iranseda.ir"

def gh_raw_url(relative_path: str) -> str:
    # Use config method for GitHub raw URL
    return config.get_github_raw_url(relative_path)

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
        if candidate.exists() and not candidate.name.endswith('.ffmpeg.failed'):
            rel = os.path.join("downloads", candidate.name)
            results.append({"type": ext.lstrip("."), "name": candidate.name, "repo_rel": rel, "raw_url": gh_raw_url(rel), "label": "زیرنویس"})
        # Cleaned transcripts in downloads/cleaned/
        cleaned_candidate = DOWNLOADS_DIR / "cleaned" / f"{stem}{ext}"
        if cleaned_candidate.exists() and not cleaned_candidate.name.endswith('.ffmpeg.failed'):
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

def get_time_based_stats():
    """Calculate time-based statistics for SRT generation"""
    from datetime import datetime, timedelta
    import os
    import glob
    
    now = datetime.now()
    today = now.date()
    yesterday = today - timedelta(days=1)
    
    # Calculate week boundaries
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    start_of_last_week = start_of_week - timedelta(days=7)
    end_of_last_week = start_of_week - timedelta(days=1)
    
    # Calculate month boundaries
    start_of_month = today.replace(day=1)
    if today.month == 12:
        start_of_next_month = today.replace(year=today.year + 1, month=1, day=1)
    else:
        start_of_next_month = today.replace(month=today.month + 1, day=1)
    end_of_month = start_of_next_month - timedelta(days=1)
    
    if today.month == 1:
        start_of_last_month = today.replace(year=today.year - 1, month=12, day=1)
    else:
        start_of_last_month = today.replace(month=today.month - 1, day=1)
    end_of_last_month = start_of_month - timedelta(days=1)
    
    # Calculate year boundaries
    start_of_year = today.replace(month=1, day=1)
    start_of_next_year = today.replace(year=today.year + 1, month=1, day=1)
    end_of_year = start_of_next_year - timedelta(days=1)
    start_of_last_year = today.replace(year=today.year - 1, month=1, day=1)
    end_of_last_year = start_of_year - timedelta(days=1)
    
    def count_srt_files_in_period(start_date, end_date):
        """Count SRT files created in a specific date range (excluding failed files)"""
        count = 0
        downloads_dir = DOWNLOADS_DIR
        if downloads_dir.exists():
            for srt_file in downloads_dir.glob("*.srt"):
                try:
                    # Skip files with .ffmpeg.failed suffix
                    if srt_file.name.endswith('.ffmpeg.failed'):
                        continue
                    # Get file modification time
                    file_time = datetime.fromtimestamp(srt_file.stat().st_mtime).date()
                    if start_date <= file_time <= end_date:
                        count += 1
                except:
                    continue
        return count
    
    stats = {
        'today': count_srt_files_in_period(today, today),
        'yesterday': count_srt_files_in_period(yesterday, yesterday),
        'this_week': count_srt_files_in_period(start_of_week, end_of_week),
        'last_week': count_srt_files_in_period(start_of_last_week, end_of_last_week),
        'this_month': count_srt_files_in_period(start_of_month, end_of_month),
        'last_month': count_srt_files_in_period(start_of_last_month, end_of_last_month),
        'this_year': count_srt_files_in_period(start_of_year, end_of_year),
        'last_year': count_srt_files_in_period(start_of_last_year, end_of_last_year),
    }
    
    return stats

def get_latest_cleaned_files(limit=10):
    """Get latest cleaned subtitle files with program information"""
    cleaned_files = []
    cleaned_dir = DOWNLOADS_DIR / "cleaned"
    
    if not cleaned_dir.exists():
        return cleaned_files
    
    # Get all cleaned files with their modification times
    file_info = []
    for srt_file in cleaned_dir.glob("*.srt"):
        try:
            # Skip files with .ffmpeg.failed suffix
            if srt_file.name.endswith('.ffmpeg.failed'):
                continue

            mod_time = datetime.fromtimestamp(srt_file.stat().st_mtime)
            file_info.append({
                'file': srt_file,
                'name': srt_file.name,
                'mod_time': mod_time,
                'size': srt_file.stat().st_size
            })
        except:
            continue
    
    # Sort by modification time (newest first)
    file_info.sort(key=lambda x: x['mod_time'], reverse=True)
    
    # Take only the requested number
    for info in file_info[:limit]:
        # Extract program info from filename (heuristic)
        filename = info['name']
        stem = pathlib.Path(filename).stem
        
        # Try to extract date and time from filename
        # Format: radio-maaref-03-11-28-15-00.srt
        parts = stem.split('-')
        if len(parts) >= 6:
            try:
                month = parts[2]
                day = parts[3]
                hour = parts[4]
                minute = parts[5]
                program_name = "برنامه رادیویی"  # Default
                
                # Try to match with known programs
                if "maaref" in stem.lower():
                    program_name = "بر كرانه نور"
                elif "ganj" in stem.lower():
                    program_name = "گنج سعادت"
                elif "porseman" in stem.lower():
                    program_name = "پرسمان"
                
                cleaned_files.append({
                    'filename': filename,
                    'program_name': program_name,
                    'date': f"{month}/{day}",
                    'time': f"{hour}:{minute}",
                    'mod_time': info['mod_time'],
                    'size': info['size'],
                    'raw_url': config.get_github_raw_url(f"downloads/cleaned/{filename}")
                })
            except:
                # Fallback for files that don't match expected format
                cleaned_files.append({
                    'filename': filename,
                    'program_name': "نامشخص",
                    'date': info['mod_time'].strftime("%m/%d"),
                    'time': info['mod_time'].strftime("%H:%M"),
                    'mod_time': info['mod_time'],
                    'size': info['size'],
                    'raw_url': config.get_github_raw_url(f"downloads/cleaned/{filename}")
                })
    
    return cleaned_files

def get_latest_programs_with_cleaned(programs, stats_by_program_id, limit=3):
    """Get latest programs that have new cleaned subtitles"""
    programs_with_cleaned = []
    
    for p in programs:
        pid = p['id']
        st = stats_by_program_id.get(pid, {})
        cleaned_count = st.get('cleaned_count', 0)
        
        if cleaned_count > 0:
            programs_with_cleaned.append({
                'id': pid,
                'name': p.get('name', '').strip(),
                'cleaned_count': cleaned_count,
                'total_sessions': st.get('total_sessions', 0),
                'last_date': st.get('last_date_disp', ''),
                'url': f"programs/{pid}.html"
            })
    
    # Sort by cleaned count (descending) and take latest
    programs_with_cleaned.sort(key=lambda x: x['cleaned_count'], reverse=True)
    return programs_with_cleaned[:limit]

def render_index(programs, stats_by_program_id):
    # Get time-based statistics
    time_stats = get_time_based_stats()
    
    # Get latest programs with cleaned subtitles
    latest_programs = get_latest_programs_with_cleaned(programs, stats_by_program_id, 3)
    
    # Get latest cleaned files
    latest_cleaned_files = get_latest_cleaned_files(10)
    
    # Build time-based stats display
    time_stats_html = f"""
    <div class="time-stats">
      <h3>📊 آمار تولید زیرنویس‌ها / Subtitle Generation Statistics</h3>
      <div class="stats-grid">
        <div class="stat-item">
          <span class="stat-label">امروز / Today:</span>
          <span class="stat-value">{time_stats['today']}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">دیروز / Yesterday:</span>
          <span class="stat-value">{time_stats['yesterday']}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">این هفته / This Week:</span>
          <span class="stat-value">{time_stats['this_week']}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">هفته گذشته / Last Week:</span>
          <span class="stat-value">{time_stats['last_week']}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">این ماه / This Month:</span>
          <span class="stat-value">{time_stats['this_month']}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">ماه گذشته / Last Month:</span>
          <span class="stat-value">{time_stats['last_month']}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">امسال / This Year:</span>
          <span class="stat-value">{time_stats['this_year']}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">سال گذشته / Last Year:</span>
          <span class="stat-value">{time_stats['last_year']}</span>
        </div>
      </div>
    </div>
    """
    
    # Build latest programs section
    latest_programs_html = ""
    if latest_programs:
        program_items = []
        for prog in latest_programs:
            program_items.append(f"""
            <div class="program-item">
              <a href="{prog['url']}" class="program-link">{html_escape(prog['name'])}</a>
              <div class="program-stats">
                <span class="cleaned-count">{prog['cleaned_count']} متن کامل</span>
                <span class="total-sessions">{prog['total_sessions']} قسمت</span>
              </div>
            </div>""")
        
        latest_programs_html = f"""
        <div class="latest-programs">
          <h3>🆕 آخرین برنامه‌های با متن کامل / Latest Programs with Cleaned Subtitles</h3>
          <div class="programs-grid">
            {''.join(program_items)}
          </div>
        </div>
        """
    
    # Build latest files section
    latest_files_html = ""
    if latest_cleaned_files:
        file_rows = []
        for file_info in latest_cleaned_files:
            file_rows.append(f"""
            <tr>
              <td><a href="{file_info['raw_url']}" target="_blank" rel="noopener" class="file-link">{html_escape(file_info['filename'])}</a></td>
              <td>{html_escape(file_info['program_name'])}</td>
              <td>{file_info['date']}</td>
              <td>{file_info['time']}</td>
              <td>{file_info['mod_time'].strftime('%Y-%m-%d %H:%M')}</td>
            </tr>""")
        
        latest_files_html = f"""
        <div class="latest-files">
          <h3>📁 آخرین فایل‌های متن کامل / Latest Cleaned Files</h3>
          <table class="files-table">
            <thead>
              <tr>
                <th>نام فایل / Filename</th>
                <th>برنامه / Program</th>
                <th>تاریخ / Date</th>
                <th>ساعت / Time</th>
                <th>آخرین تغییر / Last Modified</th>
              </tr>
            </thead>
            <tbody>
              {''.join(file_rows)}
            </tbody>
          </table>
        </div>
        """
    
    # Build table rows
    rows = []
    for p in programs:
        pid = p['id']
        title = html_escape((p.get("name") or "").strip())
        time_info = []
        if p.get("time"):
            time_info.append(format_time(p['time']))
        if p.get("time_description"):
            time_info.append(html_escape(p['time_description']))
        time_info_str = " | ".join([s for s in time_info if s])

        st = stats_by_program_id.get(pid, {})
        total_sessions = st.get('total_sessions', 0)
        sub_count = st.get('subtitle_count', 0)
        cleaned_count = st.get('cleaned_count', 0)
        first_dt_iso = st.get('first_date_iso', '')
        last_dt_iso = st.get('last_date_iso', '')
        first_dt_disp = st.get('first_date_disp', '')
        last_dt_disp = st.get('last_date_disp', '')

        rows.append(f"""
        <tr>
          <td data-label="نام"><a href="programs/{pid}.html">{title}</a></td>
          <td data-label="زمان/توضیح">{time_info_str}</td>
          <td data-label="قسمت‌ها" data-order="{total_sessions}">{total_sessions}</td>
          <td data-label="زیرنویس" data-order="{sub_count}">{sub_count}</td>
          <td data-label="متن کامل" data-order="{cleaned_count}">{cleaned_count}</td>
          <td data-label="اولین" data-order="{first_dt_iso}">{first_dt_disp}</td>
          <td data-label="آخرین" data-order="{last_dt_iso}">{last_dt_disp}</td>
        </tr>""")

    return f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>فهرست برنامه‌های رادیو ایران‌صدا</title>
<style>
body {{ font-family: 'Tahoma', 'Arial', sans-serif; margin: 24px; background: #f5f5f5; }}
.container {{ max-width: 1100px; margin: 0 auto; background: white; padding: 24px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
header {{ margin-bottom: 24px; text-align: center; }}
h1 {{ color: #2c3e50; margin-bottom: 8px; }}
.meta {{ color: #7f8c8d; font-size: 14px; }}
.time-stats {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 24px; }}
.time-stats h3 {{ margin: 0 0 16px 0; text-align: center; font-size: 18px; }}
.stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }}
.stat-item {{ background: rgba(255,255,255,0.1); padding: 12px; border-radius: 6px; text-align: center; }}
.stat-label {{ display: block; font-size: 12px; opacity: 0.9; margin-bottom: 4px; }}
.stat-value {{ display: block; font-size: 24px; font-weight: bold; }}
.latest-programs {{ background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 24px; }}
.latest-programs h3 {{ margin: 0 0 16px 0; text-align: center; font-size: 18px; }}
.programs-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }}
.program-item {{ background: rgba(255,255,255,0.15); padding: 16px; border-radius: 8px; }}
.program-link {{ color: white; text-decoration: none; font-weight: bold; font-size: 16px; display: block; margin-bottom: 8px; }}
.program-link:hover {{ color: #ffeb3b; }}
.program-stats {{ display: flex; justify-content: space-between; font-size: 14px; opacity: 0.9; }}
.cleaned-count {{ color: #4caf50; font-weight: bold; }}
.total-sessions {{ color: #2196f3; }}
.latest-files {{ background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 24px; }}
.latest-files h3 {{ margin: 0 0 16px 0; text-align: center; font-size: 18px; }}
.files-table {{ width: 100%; border-collapse: collapse; background: rgba(255,255,255,0.1); border-radius: 8px; overflow: hidden; }}
.files-table th, .files-table td {{ padding: 12px; text-align: right; border-bottom: 1px solid rgba(255,255,255,0.2); }}
.files-table th {{ background: rgba(255,255,255,0.2); font-weight: bold; }}
.files-table tr:hover {{ background: rgba(255,255,255,0.1); }}
.file-link {{ color: white; text-decoration: none; font-weight: bold; }}
.file-link:hover {{ color: #ffeb3b; }}
table {{ width: 100%; border-collapse: collapse; direction: rtl; }}
th, td {{ padding: 10px 12px; border-bottom: 1px solid #eee; text-align: right; }}
th {{ cursor: pointer; background: #f8f9fa; position: sticky; top: 0; }}
tr:hover {{ background: #fafafa; }}
.sortable::after {{ content: ' \25B2\25BC'; color: #ccc; font-size: 12px; margin-right: 6px; }}
</style>
<script>
function sortTable(n, isNumeric=false, isDate=false) {{
  const table = document.getElementById('programsTable');
  const tbody = table.tBodies[0];
  const rows = Array.from(tbody.rows);
  let dir = table.getAttribute('data-sort-dir') === 'asc' ? 'desc' : 'asc';
  table.setAttribute('data-sort-dir', dir);
  rows.sort((a, b) => {{
    const aCell = a.cells[n];
    const bCell = b.cells[n];
    const aKey = aCell.getAttribute('data-order') || aCell.textContent.trim();
    const bKey = bCell.getAttribute('data-order') || bCell.textContent.trim();
    let aVal = aKey, bVal = bKey;
    if (isNumeric) {{ aVal = parseFloat(aKey)||0; bVal = parseFloat(bKey)||0; }}
    else if (isDate) {{ aVal = aKey; bVal = bKey; }}
    else {{ aVal = aKey; bVal = bKey; }}
    if (aVal < bVal) return dir === 'asc' ? -1 : 1;
    if (aVal > bVal) return dir === 'asc' ? 1 : -1;
    return 0;
  }});
  rows.forEach(r => tbody.appendChild(r));
}}
</script>
</head>
<body>
<div class="container">
<header>
  <h1>فهرست برنامه‌های رادیو ایران‌صدا</h1>
  <div class="meta">تولید شده در {datetime.now().strftime("%Y-%m-%d %H:%M")} | تعداد برنامه‌ها: {len(programs)}</div>
</header>

{time_stats_html}

{latest_programs_html}

{latest_files_html}
<table id="programsTable" data-sort-dir="asc">
  <thead>
    <tr>
      <th class="sortable" onclick="sortTable(0, false, false)">نام</th>
      <th class="sortable" onclick="sortTable(1, false, false)">زمان/توضیح</th>
      <th class="sortable" onclick="sortTable(2, true, false)">تعداد قسمت</th>
      <th class="sortable" onclick="sortTable(3, true, false)">زیرنویس</th>
      <th class="sortable" onclick="sortTable(4, true, false)">متن کامل</th>
      <th class="sortable" onclick="sortTable(5, false, true)">اولین تاریخ</th>
      <th class="sortable" onclick="sortTable(6, false, true)">آخرین تاریخ</th>
    </tr>
  </thead>
  <tbody>
    {''.join(rows)}
  </tbody>
</table>
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
    print("🔧 Configuration:")
    config.print_config()
    print()
    
    ensure_dirs()
    
    try:
        conn = connect_db()
        print("✅ Connected to database")
        
        programs = fetch_programs(conn)
        print(f"📊 Found {len(programs)} programs")
        
        # Compute stats per program
        stats_by_program_id = {}
        for p in programs:
            sessions, _files = fetch_sessions_for_program(conn, p["id"])
            total_sessions = len(sessions)
            subtitle_count = 0
            cleaned_count = 0
            first_dt = None
            last_dt = None
            for s in sessions:
                created = s.get("created_at")
                if created:
                    dt = created if isinstance(created, datetime) else None
                    if dt is None:
                        try:
                            # Fallback parse
                            dt = datetime.fromisoformat(str(created))
                        except Exception:
                            dt = None
                    if dt is not None:
                        first_dt = dt if first_dt is None or dt < first_dt else first_dt
                        last_dt = dt if last_dt is None or dt > last_dt else last_dt
                subs = find_subtitles_for_session(s.get("filename") or "")
                if subs:
                    # Count separately by label
                    for sub in subs:
                        if sub.get("label") == "زیرنویس":
                            subtitle_count += 1
                            break
                if subs:
                    for sub in subs:
                        if sub.get("label") == "متن کامل":
                            cleaned_count += 1
                            break
            stats_by_program_id[p["id"]] = {
                "total_sessions": total_sessions,
                "subtitle_count": subtitle_count,
                "cleaned_count": cleaned_count,
                "first_date_iso": first_dt.strftime("%Y-%m-%d %H:%M:%S") if first_dt else "",
                "last_date_iso": last_dt.strftime("%Y-%m-%d %H:%M:%S") if last_dt else "",
                "first_date_disp": first_dt.strftime("%Y-%m-%d %H:%M") if first_dt else "",
                "last_date_disp": last_dt.strftime("%Y-%m-%d %H:%M") if last_dt else "",
            }

        # Generate index page
        index_html = render_index(programs, stats_by_program_id)
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
