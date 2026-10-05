#!/usr/bin/env python3
"""
fetch_media.py — re-download media for pending_download sessions and flip them
to pending_transcribe so the Whisper worker can transcribe them.

Background (2026-10-05):
  A set of sessions is dead-locked in status='pending_download' with
  is_downloaded=1 and a filename set, but the media file is NOT on disk:
    * the Go crawler only downloads rows with is_downloaded=0, so it skips them;
    * the worker only reads pending_transcribe, so it never retries them.
  The radio.iranseda.ir epgarchivePart page was previously thought to be
  fully anti-bot gated, but with allow_redirects=True (follow https->http)
  ~75% of the OLD archive links now return a full page whose
  <a class="col-plus page-loding"> hrefs (headend1/2.iranseda.ir/DLFile) still
  serve real audio bytes. ~25% still return a 15-byte JS-gate stub
  ("<!DOCTYPE html>"); those are reported and left alone.

Selection rules (must match services/whisper/common.py exactly):
  * target filename = the anchor whose Content-Disposition name equals the
    DB filename, else the first .mp4 anchor, else the first anchor.
  * file must be saved to <DOWNLOADS>/<target> and be > 100_000 bytes, which
    is what common.find_local_media requires (> 100_000).
  * after a good download: UPDATE ... SET filename=<target>, is_downloaded=1,
    status='pending_transcribe', last_error=NULL.

Safety:
  * DRY-RUN by default: fetches each page, identifies the target, does a
    1-byte range check, and prints the plan WITHOUT downloading or touching
    the DB. Pass --apply to actually download + update the DB.
  * Never touches rows not in the selected set. Never deletes anything.

Usage (run from the repo root with the crawler venv, e.g. on server 53):
  crawler/venv/bin/python3 scripts/fetch_media.py --limit 10                 # dry-run first 10
  crawler/venv/bin/python3 scripts/fetch_media.py --limit 10 --apply         # do it
  crawler/venv/bin/python3 scripts/fetch_media.py --ids 1363,2106            # specific rows
  crawler/venv/bin/python3 scripts/fetch_media.py --id-min 1800 --apply      # live zone only
  crawler/venv/bin/python3 scripts/fetch_media.py --limit 400 --apply        # full pass

Env:
  DB_HOST DB_PORT DB_USER DB_PASS DB_NAME   (defaults match server 53 radio db)
  DOWNLOADS_PATH                            (default: <repo>/downloads)
"""
import os
import re
import sys
import time
import argparse
import urllib.parse

import requests
from bs4 import BeautifulSoup
import pymysql

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_HOST = os.getenv("DB_HOST", "172.20.1.53")
DB_PORT = int(os.getenv("DB_PORT", "3308"))
DB_USER = os.getenv("DB_USER", "n8nuser")
DB_PASS = os.getenv("DB_PASS", "StrongPassword123!")
DB_NAME = os.getenv("DB_NAME", "radio")
DOWNLOADS = os.getenv("DOWNLOADS_PATH", os.path.join(REPO, "downloads"))

BASE = "https://radio.iranseda.ir"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
MIN_BYTES = 100_000          # must match common.find_local_media threshold
STUB_MAX_LEN = 200           # body shorter than this with no DLFile anchor == JS-gate stub
PAGE_DELAY = float(os.getenv("PAGE_DELAY", "1.5"))
DL_DELAY = float(os.getenv("DL_DELAY", "2.0"))
TIMEOUT = 40


def norm(name):
    # exactly like common.filename_from_content_disposition
    return re.sub(r"[/:\s]+", "-", name.strip().strip('"'))


def db_conn():
    return pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER,
                           password=DB_PASS, database=DB_NAME,
                           charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)


def select_rows(cur, ids, limit, id_min=0):
    if ids:
        id_list = [int(x) for x in ids.split(",") if x.strip()]
        ph = ",".join(["%s"] * len(id_list))
        cur.execute("SELECT id, filename, link FROM radio_program_sessions "
                    "WHERE id IN (%s)" % ph, id_list)
        return cur.fetchall()
    sql = ("SELECT id, filename, link FROM radio_program_sessions "
           "WHERE status='pending_download' AND link IS NOT NULL AND link<>''")
    params = []
    if id_min:
        sql += " AND id >= %s"
        params.append(id_min)
    sql += " ORDER BY id"
    if limit:
        sql += " LIMIT %s"
        params.append(limit)
    cur.execute(sql, tuple(params))
    return cur.fetchall()


def page_anchors(sess):
    """Return (ok, anchors, reason). anchors = list of (disp_name, url)."""
    link = sess["link"].replace("..", "", 1)
    url = BASE + link
    try:
        r = get_session().get(url, allow_redirects=True, timeout=TIMEOUT)
    except Exception as e:
        return False, [], "http-error:%r" % (e,)
    if len(r.text) < STUB_MAX_LEN:
        return False, [], "stub(len=%d)" % len(r.text)
    soup = BeautifulSoup(r.text, "html.parser")
    anchors = []
    for a in soup.find_all("a", class_="col-plus"):
        if "page-loding" not in (a.get("class") or []):
            continue
        href = a.get("href")
        if not href or "DLFile" not in href:
            continue
        full = urllib.parse.urljoin(r.url, href)
        name, _ = disp_name(get_session(), full)
        if name:
            anchors.append((name, full))
    if not anchors:
        return False, [], "no-dlfile-anchors(len=%d)" % len(r.text)
    return True, anchors, ""


def disp_name(s, url):
    """(normalized Content-Disposition filename, content_type) via 1-byte range."""
    try:
        r = s.get(url, stream=True, headers={"Range": "bytes=0-0"},
                  allow_redirects=True, timeout=TIMEOUT)
    except Exception:
        return None, None
    cd = r.headers.get("Content-Disposition", "")
    ct = r.headers.get("Content-Type", "")
    r.close()
    m = re.search(r"filename\*?=(?:UTF-8\x27\x27)?\"?([^\";]+)", cd)
    if not m:
        return None, ct
    return norm(m.group(1)), ct


def pick_target(db_filename, anchors):
    """(target_name, url) — prefer the anchor matching the DB filename."""
    if db_filename:
        for name, url in anchors:
            if name == db_filename:
                return db_filename, url
    for name, url in anchors:
        if name.endswith(".mp4"):
            return name, url
    if anchors:
        return anchors[0]
    return None, None


def stream_download(sess, url, target):
    """Stream to <DOWNLOADS>/<target>.part then rename. Returns (ok, bytes)."""
    dest = os.path.join(DOWNLOADS, target)
    part = dest + ".part"
    if os.path.exists(dest) and os.path.getsize(dest) > MIN_BYTES:
        return True, os.path.getsize(dest)      # already have it
    try:
        with get_session().get(url, stream=True, allow_redirects=True,
                               timeout=120) as r:
            if r.status_code != 200:
                return False, 0
            with open(part, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
    except Exception:
        if os.path.exists(part):
            os.remove(part)
        return False, 0
    size = os.path.getsize(part) if os.path.exists(part) else 0
    if size <= MIN_BYTES:
        if os.path.exists(part):
            os.remove(part)
        return False, size
    os.replace(part, dest)
    return True, size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--id-min", type=int, default=0, dest="id_min",
                    help="only rows with id >= this (e.g. 1800 to target the live zone)")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    global _S
    _S = requests.Session()
    _S.headers.update({"User-Agent": UA, "Accept": "*/*"})

    conn = db_conn()
    cur = conn.cursor()
    rows = select_rows(cur, args.ids, args.limit, args.id_min)
    print("selected %d rows | mode=%s | downloads=%s"
          % (len(rows), "APPLY" if args.apply else "DRY-RUN", DOWNLOADS))

    n_stub = n_ok = n_fail = n_done = 0
    bytes_total = 0
    for r in rows:
        sid, fn, link = r["id"], (r["filename"] or ""), r["link"]
        tag = fn if fn else "(no-filename e=%s)" % e_of(link)
        ok, anchors, reason = page_anchors(r)
        if not ok:
            n_stub += 1
            print("  [%s] %s  STUB/SKIP: %s" % (sid, tag, reason))
            time.sleep(PAGE_DELAY)
            continue
        target, url = pick_target(fn, anchors)
        if not target:
            n_fail += 1
            print("  [%s] %s  NO-TARGET" % (sid, tag))
            continue
        if target != fn:
            print("  [%s] %s  -> name shift: db=%r target=%r" % (sid, sid, fn, target))
        if not args.apply:
            n_ok += 1
            print("  [%s] %s  READY target=%s" % (sid, tag, target))
            time.sleep(PAGE_DELAY)
            continue
        good, size = stream_download(r, url, target)
        if not good:
            n_fail += 1
            print("  [%s] %s  DOWNLOAD-FAIL size=%d" % (sid, tag, size))
            time.sleep(DL_DELAY)
            continue
        cur.execute("UPDATE radio_program_sessions "
                    "SET filename=%s, is_downloaded=1, status='pending_transcribe', "
                    "last_error=NULL WHERE id=%s", (target, sid))
        conn.commit()
        n_done += 1
        bytes_total += size
        print("  [%s] %s  OK %d bytes -> pending_transcribe" % (sid, tag, size))
        time.sleep(DL_DELAY)

    conn.close()
    print("\nSUMMARY selected=%d ok/ready=%d stub=%d fail=%d"
          % (len(rows), (n_ok if not args.apply else n_done), n_stub, n_fail))
    if args.apply:
        print("  flipped to pending_transcribe: %d (~%.2f MB)"
              % (n_done, bytes_total / 1e6))
    else:
        print("  DRY-RUN: re-run with --apply to download + flip the READY rows")


def e_of(link):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
    return q.get("e", ["?"])[0]


_S = None


def get_session():
    return _S


if __name__ == "__main__":
    main()
