import os
import re
import requests
from bs4 import BeautifulSoup
import pymysql
from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qs
from datetime import timedelta

BASE_DOMAIN = "https://radio.iranseda.ir"

# بارگذاری متغیرهای محیطی
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

conn = pymysql.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASS"),
    database=os.getenv("DB_NAME"),
    charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor
)
cursor = conn.cursor()

def get_soup(url):
    response = requests.get(url)
    response.encoding = 'utf-8'
    return BeautifulSoup(response.text, 'html.parser')

def get_active_program(url):
    cursor.execute(
        """
        SELECT id, name, time, start, time_description, description, radio, radio_id
        FROM radio_programs
        WHERE url = %s AND IFNULL(is_legacy, 0) = 0
        ORDER BY id DESC
        LIMIT 1
        """,
        (url,),
    )
    return cursor.fetchone()


def mark_program_legacy(program_id):
    cursor.execute(
        """
        UPDATE radio_programs
        SET is_legacy = 1,
            legacy_expires_at = NOW()
        WHERE id = %s
        """,
        (program_id,),
    )
    conn.commit()

def extract_duration(text):
    match = re.search(r'به مدت\s*(\d{1,4})\s*دقیقه', text)
    if match:
        total_minutes = int(match.group(1))
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours:02d}:{minutes:02d}:00"
    return None

def extract_start_time(text):
    match = re.search(r'ساعت\s*(\d{1,2}:\d{2})', text)
    if match:
        return match.group(1) + ":00"
    return None

def extract_radio_name(soup):
    radio_tag = soup.select_one('div.BaseName strong a')
    return radio_tag.get_text(strip=True) if radio_tag else None

def extract_radio_id(url):
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if 'ch' in query:
        try:
            return int(query['ch'][0])
        except ValueError:
            return None
    return None

def save_program(name, url, time_desc, description, duration, start_time, radio, radio_id):
    sql = """
        INSERT INTO radio_programs
        (name, url, time_description, description, time, start, radio, radio_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    cursor.execute(sql, (name, url, time_desc, description, duration, start_time, radio, radio_id))
    conn.commit()
    print(f"✅ Saved: {name} | duration: {duration} | start: {start_time} | radio: {radio} | radio_id: {radio_id}")

def update_program(name, url, time_desc, description, duration, start_time, radio, radio_id):
    sql = """
        UPDATE radio_programs
        SET name = %s,
            time_description = %s,
            description = %s,
            time = %s,
            start = %s,
            radio = %s,
            radio_id = %s
        WHERE url = %s
    """
    cursor.execute(sql, (name, time_desc, description, duration, start_time, radio, radio_id, url))
    conn.commit()
    print(f"🔄 Updated program: {name} | url: {url}")


def fill_missing_fields(program, duration, start_time, time_desc, description, radio, radio_id):
    updates = {}
    if not program.get('time') and duration:
        updates['time'] = duration
    if not program.get('start') and start_time:
        updates['start'] = start_time
    if (not program.get('time_description') or not program['time_description'].strip()) and time_desc:
        updates['time_description'] = time_desc
    if (not program.get('description') or not program['description'].strip()) and description:
        updates['description'] = description
    if not program.get('radio') and radio:
        updates['radio'] = radio
    if not program.get('radio_id') and radio_id is not None:
        updates['radio_id'] = radio_id

    if updates:
        set_clause = ", ".join(f"{field} = %s" for field in updates.keys())
        values = list(updates.values()) + [program['id']]
        cursor.execute(f"UPDATE radio_programs SET {set_clause} WHERE id = %s", values)
        conn.commit()
        print(f"🩹 Filled missing fields for '{program.get('name', '')}' ({program['id']})")
        return True
    return False


def has_schedule_change(program, duration, start_time, time_desc, radio, radio_id):
    checks = [
        ('time', duration),
        ('start', start_time),
        ('time_description', time_desc),
        ('radio', radio),
        ('radio_id', radio_id),
    ]
    for field, new_value in checks:
        old_value = program.get(field)
        if old_value and new_value and str(old_value).strip() != str(new_value).strip():
            return True
    return False

def extract_program_links_from_file(filepath="crawl_links.txt"):
    with open(filepath, "r", encoding="utf-8") as file:
        links = [line.strip() for line in file if line.strip()]
    return links

def crawl(overwrite=False):
    program_urls = extract_program_links_from_file()

    for prog_url in program_urls:
        print(f"🔍 Checking program page: {prog_url}")
        prog_soup = get_soup(prog_url)

        name_tag = prog_soup.select_one('h1.prog-name')
        name = name_tag.get_text(strip=True) if name_tag else ''

        time_tag = prog_soup.select_one('h2.guide-prog')
        time_desc = time_tag.get_text(strip=True) if time_tag else ''

        desc_tag = prog_soup.select_one('div.col-plus-md-9 p')
        description = desc_tag.get_text(strip=True) if desc_tag else ''
        if not description:
            description = "none"

        radio = extract_radio_name(prog_soup)
        radio_id = extract_radio_id(prog_url)
        duration = extract_duration(time_desc)
        start_time = extract_start_time(time_desc)

        archive_links = prog_soup.select('a[href*="Program/?VALID=TRUE"]')

        for a in archive_links:
            archive_url = BASE_DOMAIN + a.get('href')[2:]
            existing = get_active_program(archive_url)
            if not existing:
                save_program(name, archive_url, time_desc, description, duration, start_time, radio, radio_id)
            else:
                if has_schedule_change(existing, duration, start_time, time_desc, radio, radio_id):
                    mark_program_legacy(existing['id'])
                    save_program(name, archive_url, time_desc, description, duration, start_time, radio, radio_id)
                else:
                    filled = fill_missing_fields(existing, duration, start_time, time_desc, description, radio, radio_id)
                    if not filled:
                        print(f"⚠️ No changes for existing program: {archive_url}")

# برای اجرای crawl با بازنویسی رکوردها، از این استفاده کن:
# crawl(overwrite=True)

# یا فقط برای اضافه کردن رکوردهای جدید (بدون بازنویسی)
# crawl()

crawl()

cursor.close()
conn.close()
