"""
iranseda_site.py — read-only scraper for radio.iranseda.ir (HTML, no JSON API).

Stdlib only (urllib + html.parser): no third-party deps, so it runs in the
dashboard venv, the crawler venv, or a bare python. Every function here is a
pure fetch+parse and is safe to call repeatedly (polite timeouts, no writes).

Site structure (verified against the live site):
  radiolist/?VALID=TRUE
      all 75 channels: <a ... href="../live/?VALID=TRUE&ch=14">رادیو معارف</a>
      grouped in <ul id="m1"> (سراسری), <ul id="m3"> (استانی), <ul id="m2"> (نما).
  programlist/?VALID=TRUE&ch=14
      every program on the channel:
      <a href="../Program/?VALID=TRUE&ch=14&m=044002">name</a>
      `m` = STABLE 8-digit program id (embedded in every episode card's image
      URL too). This is the program->archive key.
  Program/?VALID=TRUE&ch=14&m=044002&pn=N
      archived episodes, 20/page, NEWEST FIRST. Each card:
      <a href="../epgarchivePart/?VALID=TRUE&ch=14&e=<eventId>">...
        <h4 class="ott-sub-name...">episode title (often = program name)</h4>
        <p ...>شنبه 28 مهر 1405 — 14:30</p>  (Jalali date + Gregorian-ish time)
      `e` = PER-BROADCAST event id (changes every air date; never stable per
      program). Pagination: nav#pagination links with pn=1..N.
  epgarchivePart/?VALID=TRUE&ch=14&e=<eventId>
      single episode. The download modal (#myModal1) holds:
      <a class="col-plus page-loding" href="http://headend2.iranseda.ir/DLFile/?VALID=TRUE&vid=<id>_227">
      vid format <mediaId>_<quality>: 227=.mp3, 226=.mp4.

The dashboard's discovery UI, the pipeline's seed job, and any manual probe all
go through this module — there is exactly one place that talks to the site.
"""
import os
import re
import ssl
import urllib.request
import urllib.parse
from datetime import datetime, date

BASE = "https://radio.iranseda.ir"
UA = "Mozilla/5.0 (compatible; iranseda-dashboard-discovery/1.0)"

CHANNEL_GROUPS = [
    ("m1", "رادیو سراسری"),
    ("m3", "رادیو استانی"),
    ("m2", "رادیو نما"),
]

# ---------------------------------------------------------------------------
# transport
# ---------------------------------------------------------------------------

_SSL_CTX = None
_SSL_DISABLED = os.environ.get("IRANSEDA_NO_SSL_VERIFY", "") == "1"


def http_get(url, timeout=30):
    global _SSL_CTX
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    if _SSL_DISABLED:
        if _SSL_CTX is None:
            _SSL_CTX = ssl.create_default_context()
            _SSL_CTX.check_hostname = False
            _SSL_CTX.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
            return r.read().decode("utf-8", "replace")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# channels
# ---------------------------------------------------------------------------

def list_channels():
    """All channels: [{ch:int, name:str, group:str}]. Order: سراسری/استانی/نما."""
    html = http_get(f"{BASE}/radiolist/?VALID=TRUE")
    out = []
    for ul_id, group in CHANNEL_GROUPS:
        m = re.search(r'<ul id="%s".*?</ul>' % ul_id, html, re.S)
        if not m:
            continue
        block = m.group(0)
        for href, name in re.findall(
            r'<a[^>]+href="[^"]*\bch=(\d+)[^"]*"[^>]*>(.*?)</a>', block, re.S
        ):
            name = re.sub(r"<[^>]+>", "", name)
            name = re.sub(r"\s+", " ", name).strip()
            if name:
                out.append({"ch": int(href), "name": name, "group": group})
    # de-dup by ch (keep first)
    seen, dedup = set(), []
    for c in out:
        if c["ch"] in seen:
            continue
        seen.add(c["ch"])
        dedup.append(c)
    return dedup


# ---------------------------------------------------------------------------
# programs (per channel)
# ---------------------------------------------------------------------------

def list_programs(ch, page=1):
    """One page of a channel's program catalog:
    [{m, name, url}] (url = absolute Program page). 50/page on the live site.
    Raises RuntimeError when the page is empty/invalid (used to stop paging)."""
    url = f"{BASE}/programlist/?VALID=TRUE&ch={ch}"
    if page > 1:
        url += f"&pn={page}"
    html = http_get(url)
    items, seen = [], set()
    for href, name in re.findall(
        r'<a[^>]+href="[^"]*Program/\?VALID=TRUE&ch=\d+&m=(\d+)[^"]*"[^>]*>(.*?)</a>',
        html, re.S,
    ):
        name = re.sub(r"<[^>]+>", "", name)
        name = re.sub(r"\s+", " ", name).strip()
        if not name or m_seen(seen, href):
            continue
        seen.add(href)
        # href looks like "../Program/?VALID=TRUE&ch=14&m=044002".
        # m is stored zero-padded to 8 digits (DB convention — see radio.sql).
        items.append({"m": int(href), "name": name,
                      "url": f"{BASE}/Program/?VALID=TRUE&ch={ch}&m={int(href):08d}"})
    if not items:
        raise RuntimeError(f"programlist page {page} for ch={ch} had no program links")
    return items


def m_seen(seen, href):
    return href in seen


def list_programs_all(ch):
    """Full catalog of a channel. Follows pagination until a page is empty.
    Returns {count:int, programs:[{m,name,url}], pages:int}."""
    programs, pages, seen = [], 0, set()
    while pages < 40:  # hard cap (ch=14 real max is ~12 pages)
        try:
            page_items = list_programs(ch, pages + 1)
        except RuntimeError:
            break
        pages += 1
        fresh = [p for p in page_items if p["m"] not in seen]
        if not fresh:
            break
        for p in fresh:
            seen.add(p["m"])
            programs.append(p)
    return {"count": len(programs), "programs": programs, "pages": pages}


def search_programs(ch, needle):
    """Filter a channel's full catalog by a substring (Persian name). Cheap:
    the catalog is ~1-12 pages; cached by the dashboard for 1h."""
    all_p = list_programs_all(ch)
    needle = (needle or "").strip()
    progs = all_p["programs"]
    if needle:
        progs = [p for p in progs if needle in p["name"]]
    return {"count": len(progs), "programs": progs, "pages": all_p["pages"]}


# ---------------------------------------------------------------------------
# episodes (per program, newest first)
# ---------------------------------------------------------------------------

def _page_url(m, ch, page=1):
    url = f"{BASE}/Program/?VALID=TRUE&ch={ch}&m={m}"
    if page > 1:
        url += f"&pn={page}"
    return url


def parse_episode_cards(html):
    """Parse one Program page into 20 episode records, newest first.
    Card layout (live site):
      <a ... href="../epgarchivePart/?VALID=TRUE&ch=14&e=<id>">
        <div class="dt-title fa-number"><h2>29</h2>
          <h4>مهر<span class="clearfix">1405 (ساعت 1:25)</span></h4></div>
        <p class="ott-name ...">title (often empty)</p>
      </a>
    The h4 contains the month name, then a <span> with `YYYY (ساعت H:MM)`.
    """
    cards = re.findall(
        r'<a[^>]+href="[^"]*epgarchivePart/\?[^"]*ch=(\d+)&e=(\d+)[^"]*"[^>]*>(.*?)</a>',
        html, re.S,
    )
    out = []
    for ch, e, body in cards:
        day = re.search(r'<h2>(\d{1,2})</h2>', body)
        h4 = re.search(r'<h4>(.*?)</h4>', body, re.S)
        h4t = re.sub(r"<[^>]+>", " ", h4.group(1)) if h4 else ""
        h4t = re.sub(r"\s+", " ", h4t).strip()
        # h4 text after tag-strip: "مهر 1405 (ساعت 1:25)"
        yr = re.search(r"(\d{3,4})\s*\(ساعت\s*(\d{1,2}:\d{2})\)", h4t)
        month = ""
        m2 = re.match(r"^(.*?)\s*\d{3,4}", h4t)
        if m2:
            month = m2.group(1).strip()
        name = re.search(r'ott-name[^>]*>(.*?)</p>', body, re.S)
        title = re.sub(r"<[^>]+>", " ", name.group(1)) if name else ""
        title = re.sub(r"\s+", " ", title).strip()
        date_jalali = ""
        if day and month:
            date_jalali = f"{day.group(1)} {month}"
            if yr:
                date_jalali += f" {yr.group(1)}"
        out.append({
            "e": int(e),
            "title": title,
            "date_jalali": date_jalali,
            "year": int(yr.group(1)) if yr else None,
            "time": yr.group(2) if yr else "",
            "url": f"../epgarchivePart/?VALID=TRUE&ch={ch}&e={e}",
        })
    return out


def _max_page(html):
    """Highest pn linked in the pagination nav (the last page)."""
    pns = [int(x) for x in re.findall(r"pn=(\d+)", html)]
    return max(pns) if pns else 1


def list_episodes(m, ch, page=1):
    """One page (20) of a program's archived episodes, newest first."""
    return parse_episode_cards(http_get(_page_url(m, ch, page)))


def _page_total(m, ch):
    """Total pages for a program (last page number on the nav)."""
    return _max_page(http_get(_page_url(m, ch, 1)))


def find_archive_start(m, ch, max_pages=4000):
    """Locate the oldest archived episodes by binary-searching the pages
    (newest-first list). ~log2(N) fetches regardless of archive depth.
    Returns {oldest_jalali, oldest_year, pages_total, oldest:[episodes]}."""
    hi = min(_page_total(m, ch), max_pages)
    lo = 1
    last_items = []
    while lo < hi:
        mid = (lo + hi + 1) // 2
        items = parse_episode_cards(http_get(_page_url(m, ch, mid)))
        if items:
            lo = mid          # page mid exists -> oldest is at >= mid
            last_items = items
        else:
            hi = mid - 1
    if not last_items:
        last_items = parse_episode_cards(http_get(_page_url(m, ch, 1)))
    years = [i["year"] for i in last_items if i.get("year")]
    return {
        "oldest_jalali": last_items[-1]["date_jalali"] if last_items else "",
        "oldest_year": min(years) if years else None,
        "pages_total": hi,
        "oldest": last_items[-20:],
    }


# ---------------------------------------------------------------------------
# episode download link (the modal on the archive page)
# ---------------------------------------------------------------------------

def episode_meta(e, ch):
    """Program metadata from an episode's archive page — everything the
    one-click add needs to build a radio_programs row:
    {name, start, duration, time_description, radio, url}.
    The page header reads e.g.:
      <h1 class="prog-name">بر بال سخن</h1>
      <h2 class="guide-prog">... چهارشنبه 29 مهر 1405 ساعت 01:25 به مدت 30 دقیقه
    and <div class="BaseName"><strong><a>رادیو معارف</a></strong></div>."""
    url = f"{BASE}/epgarchivePart/?VALID=TRUE&ch={ch}&e={e}"
    html = http_get(url)
    name = ""
    n = re.search(r'prog-name[^>]*>(.*?)</h1>', html, re.S)
    if n:
        name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", n.group(1))).strip()
    time_desc = ""
    g = re.search(r'guide-prog[^>]*>(.*?)</h2>', html, re.S)
    if g:
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", g.group(1))).strip()
        # the page sometimes carries comment-markup residue inside the tag
        time_desc = re.sub(r"-\s*->\s*", " ", txt)
        time_desc = re.sub(r"\s+", " ", time_desc).strip()
        # collapse a phrase immediately repeated by the page (e.g. "به مدت 30 دقیقه")
        time_desc = re.sub(r"(\bبه مدت\s*\d+\s*دقیقه\b)\s*\1", r"\1", time_desc)
    start = None
    s = re.search(r"ساعت\s*(\d{1,2}:\d{2})", time_desc)
    if s:
        start = s.group(1) + ":00"
    duration = None
    d = re.search(r"به مدت\s*(\d{1,4})\s*دقیقه", time_desc)
    if d:
        mins = int(d.group(1))
        duration = f"{mins // 60:02d}:{mins % 60:02d}:00"
    radio = None
    r = re.search(r'BaseName[^>]*>(?:\s|<strong>)*<a[^>]*>(.*?)</a>', html, re.S)
    if r:
        radio = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.group(1))).strip()
    return {"name": name, "start": start, "duration": duration,
            "time_description": time_desc or None, "radio": radio, "url": url}


def episode_download_link(e, ch):
    """Direct audio URL(s) for one episode (from the download modal).
    The page carries both the mp3 (_227) and mp4 (_226) DLFile links; the
    first pair belongs to THIS episode. Returns {mp3, mp4, vid}."""
    html = http_get(f"{BASE}/epgarchivePart/?VALID=TRUE&ch={ch}&e={e}")
    vids = re.findall(r"DLFile/\?VALID=TRUE&vid=(\d+)_(22[67])", html)
    if not vids:
        raise RuntimeError(f"no DLFile link found for e={e}")
    mp3 = mp4 = None
    for vid, quality in vids:
        if quality == "227" and mp3 is None:
            mp3 = f"http://headend2.iranseda.ir/DLFile/?VALID=TRUE&vid={vid}_{quality}"
        elif quality == "226" and mp4 is None:
            mp4 = f"http://headend2.iranseda.ir/DLFile/?VALID=TRUE&vid={vid}_{quality}"
    if not mp3 and not mp4:
        raise RuntimeError(f"no usable DLFile link for e={e}")
    return {"mp3": mp3, "mp4": mp4, "vid": vids[0][0]}


# ---------------------------------------------------------------------------
# CLI: manual probes (python iranseda_site.py <cmd> ...)
# ---------------------------------------------------------------------------

def _main():
    import json
    import sys
    args = sys.argv[1:]
    if not args or args[0] not in (
        "channels", "programs", "episodes", "episode-meta", "archive-start",
        "download-link",
    ):
        print(__doc__)
        sys.exit(1)
    cmd = args[0]
    if cmd == "channels":
        out = list_channels()
    elif cmd == "programs":
        ch = int(args[1])
        q = args[2] if len(args) > 2 else ""
        out = search_programs(ch, q)
    elif cmd == "episodes":
        m, ch = int(args[1]), int(args[2])
        page = int(args[3]) if len(args) > 3 else 1
        out = list_episodes(m, ch, page)
    elif cmd == "episode-meta":
        e, ch = int(args[1]), int(args[2])
        out = episode_meta(e, ch)
    elif cmd == "archive-start":
        m, ch = int(args[1]), int(args[2])
        out = find_archive_start(m, ch)
    elif cmd == "download-link":
        e, ch = int(args[1]), int(args[2])
        out = episode_download_link(e, ch)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
