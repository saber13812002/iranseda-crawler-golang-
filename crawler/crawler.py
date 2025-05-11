import requests
from bs4 import BeautifulSoup
import pymysql

BASE_LIST_URL = "https://radio.iranseda.ir/epgList/?VALID=TRUE&ch=14"
BASE_DOMAIN = "https://radio.iranseda.ir"

# اتصال به پایگاه داده
conn = pymysql.connect(
    host='localhost',
    user='root',
    password='',
    database='radio',
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

def save_program(name, url, time_desc, description):
    sql = """
        INSERT INTO radio_programs (name, url, time_description, description)
        VALUES (%s, %s, %s, %s)
    """
    cursor.execute(sql, (name, url, time_desc, description))
    conn.commit()
    print(f"✅ New program saved: {name}")


def extract_program_links_from_file(filepath="crawl_links.txt"):
    with open(filepath, "r", encoding="utf-8") as file:
        links = [line.strip() for line in file if line.strip()]
    return links


def crawl():
    program_urls = extract_program_links_from_file()

    for prog_url in program_urls:
        print(f"🔍 Checking program page: {prog_url}")
        prog_soup = get_soup(prog_url)

        # استخراج نام برنامه
        name_tag = prog_soup.select_one('h1.prog-name')
        name = name_tag.get_text(strip=True) if name_tag else ''

        # استخراج توضیح زمانی
        time_tag = prog_soup.select_one('h2.guide-prog')
        time_desc = time_tag.get_text(strip=True) if time_tag else ''

        # استخراج description
        desc_tag = prog_soup.select_one('div.col-plus-md-9 p')
        description = desc_tag.get_text(strip=True) if desc_tag else ''
        # if description is empty, set it to time_desc
        if not description:
            description = "none"

        # حالا دنبال آرشیو برنامه می‌گردیم
        archive_links = prog_soup.select('a[href*="Program/?VALID=TRUE"]')
        #remove first two characters from archive_links from a tag


        for a in archive_links:
            archive_url = BASE_DOMAIN + a.get('href')[2:]
            if not is_url_exists(archive_url):
                save_program(name, archive_url, time_desc, description)
            else:
                print(f"⚠️ Already exists in DB: {archive_url}")

crawl()

cursor.close()
conn.close()
