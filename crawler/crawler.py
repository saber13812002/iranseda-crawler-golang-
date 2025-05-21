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
    charset='utf8mb4'
)
cursor = conn.cursor()

def get_soup(url):
    response = requests.get(url)
    response.encoding = 'utf-8'
    return BeautifulSoup(response.text, 'html.parser')

def is_url_exists(url):
    cursor.execute("SELECT COUNT(*) FROM radio_programs WHERE url = %s", (url,))
    return cursor.fetchone()[0] > 0

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
            exists = is_url_exists(archive_url)
            if exists and overwrite:
                update_program(name, archive_url, time_desc, description, duration, start_time, radio, radio_id)
            elif not exists:
                save_program(name, archive_url, time_desc, description, duration, start_time, radio, radio_id)
            else:
                print(f"⚠️ Already exists (skipped): {archive_url}")

# برای اجرای crawl با بازنویسی رکوردها، از این استفاده کن:
# crawl(overwrite=True)

# یا فقط برای اضافه کردن رکوردهای جدید (بدون بازنویسی)
# crawl()

crawl(overwrite=True)

cursor.close()
conn.close()
