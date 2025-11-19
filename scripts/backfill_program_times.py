#!/usr/bin/env python3
"""
Backfill and monitor radio_programs schedule metadata.

- Fills empty time/start/time_description fields by re-reading IranSeda pages
- Detects schedule changes and marks previous rows as legacy while inserting new active rows
"""

import os
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

import pymysql
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qs

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

BASE_DOMAIN = "https://radio.iranseda.ir"


def db_connection():
    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        database=os.getenv("DB_NAME"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def get_active_programs(cursor):
    cursor.execute(
        """
        SELECT id, name, url, time, start, time_description,
               description, radio, radio_id
        FROM radio_programs
        WHERE IFNULL(is_legacy, 0) = 0
        ORDER BY id
        """
    )
    return cursor.fetchall()


def get_soup(url: str) -> Optional[BeautifulSoup]:
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"❌ Failed to fetch {url}: {exc}")
        return None
    response.encoding = "utf-8"
    return BeautifulSoup(response.text, "html.parser")


def extract_duration(text: str) -> Optional[str]:
    match = re.search(r"به مدت\s*(\d{1,4})\s*دقیقه", text or "")
    if match:
        total_minutes = int(match.group(1))
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours:02d}:{minutes:02d}:00"
    return None


def extract_start_time(text: str) -> Optional[str]:
    match = re.search(r"ساعت\s*(\d{1,2}:\d{2})", text or "")
    if match:
        return match.group(1) + ":00"
    return None


def extract_radio_name(soup: BeautifulSoup) -> Optional[str]:
    radio_tag = soup.select_one("div.BaseName strong a")
    return radio_tag.get_text(strip=True) if radio_tag else None


def extract_radio_id(url: str) -> Optional[int]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "ch" in query:
        try:
            return int(query["ch"][0])
        except ValueError:
            return None
    return None


def fetch_program_metadata(url: str) -> Optional[Dict[str, Optional[str]]]:
    soup = get_soup(url)
    if not soup:
        return None

    name_tag = soup.select_one("h1.prog-name")
    time_tag = soup.select_one("h2.guide-prog")
    desc_tag = soup.select_one("div.col-plus-md-9 p")

    time_desc = time_tag.get_text(strip=True) if time_tag else ""
    duration = extract_duration(time_desc)
    start_time = extract_start_time(time_desc)
    description = desc_tag.get_text(strip=True) if desc_tag else ""
    if not description:
        description = "none"

    return {
        "name": name_tag.get_text(strip=True) if name_tag else "",
        "url": url,
        "time_description": time_desc,
        "description": description,
        "time": duration,
        "start": start_time,
        "radio": extract_radio_name(soup),
        "radio_id": extract_radio_id(url),
    }


def mark_program_legacy(cursor, program_id: int):
    cursor.execute(
        """
        UPDATE radio_programs
        SET is_legacy = 1,
            legacy_expires_at = NOW()
        WHERE id = %s
        """,
        (program_id,),
    )


def insert_program(cursor, data: Dict[str, Optional[str]]) -> int:
    cursor.execute(
        """
        INSERT INTO radio_programs
        (name, url, time, time_description, description,
         start, radio, radio_id, is_legacy)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0)
        """,
        (
            data.get("name"),
            data.get("url"),
            data.get("time"),
            data.get("time_description"),
            data.get("description"),
            data.get("start"),
            data.get("radio"),
            data.get("radio_id"),
        ),
    )
    return cursor.lastrowid


def update_missing_fields(cursor, program_id: int, updates: Dict[str, Optional[str]]):
    set_clause = ", ".join(f"{field} = %s" for field in updates.keys())
    values = list(updates.values())
    values.append(program_id)
    cursor.execute(
        f"UPDATE radio_programs SET {set_clause} WHERE id = %s",
        values,
    )


def compare_fields(
    existing: Dict[str, Optional[str]], latest: Dict[str, Optional[str]]
) -> Tuple[Dict[str, Tuple[Optional[str], Optional[str]]], Dict[str, Optional[str]]]:
    """
    Returns (changed_fields, missing_updates)
    """
    fields_to_compare = ["time", "start", "time_description", "radio", "radio_id"]
    changed = {}
    missing = {}

    for field in fields_to_compare:
        old_val = existing.get(field)
        new_val = latest.get(field)
        if not old_val and new_val:
            missing[field] = new_val
            continue
        if old_val and new_val:
            if str(old_val).strip() != str(new_val).strip():
                changed[field] = (old_val, new_val)

    if not existing.get("description") and latest.get("description"):
        missing["description"] = latest["description"]
    if not existing.get("name") and latest.get("name"):
        missing["name"] = latest["name"]

    return changed, missing


def process_program(cursor, program: Dict[str, Optional[str]]):
    metadata = fetch_program_metadata(program["url"])
    if not metadata:
        return

    changed, missing = compare_fields(program, metadata)

    if missing and not changed:
        update_missing_fields(cursor, program["id"], missing)
        print(f"🩹 Filled missing fields for program #{program['id']} ({program['name']})")
        return

    if changed:
        mark_program_legacy(cursor, program["id"])
        new_id = insert_program(cursor, metadata)
        print(
            f"♻️  Detected schedule change for '{program['name']}' "
            f"(id {program['id']} → new id {new_id})"
        )
        for field, (old, new) in changed.items():
            print(f"   - {field}: {old} → {new}")
        return

    # No action needed
    print(f"✅ No change for '{program['name']}' (id {program['id']})")


def main():
    conn = db_connection()
    try:
        with conn.cursor() as cursor:
            programs = get_active_programs(cursor)
            print(f"🔍 Processing {len(programs)} active programs...")
            for program in programs:
                process_program(cursor, program)
                conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()

