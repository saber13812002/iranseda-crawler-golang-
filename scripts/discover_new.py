"""
discover_new.py — periodic discovery: find NEW archive episodes for every
active program (is_legacy=0) and add them to radio_program_sessions.

This is the "periodic checks" half of the automation: the one-click add seeds
the chosen start point once; this script keeps each program current on every
pipeline run by scanning the program's archive page(s) and inserting any
episode that isn't already in the DB.

It reuses the exact same queue (radio_program_sessions, status=pending_download)
that scan.go / download_db.go / the whisper worker consume — no duplicate
pipeline. Bounded by NEW_SCAN_PAGES (default 14 = ~280 most-recent episodes per
program, plenty for a daily cadence; programs that missed more than that fall
back to the monthly backfill).

Run (server 53):  python3 scripts/discover_new.py
Env: NEW_SCAN_PAGES (default 14). Reads DB settings from ./.env.
"""
import os
import re
import sys
import time
import pymysql
import pymysql.cursors

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, R)
import iranseda_site as site  # noqa: E402


def load_env():
    env = {}
    ep = os.path.join(R, ".env")
    if os.path.exists(ep):
        for line in open(ep, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def db_conn():
    env = load_env()
    return pymysql.connect(
        host=os.environ.get("DB_HOST") or env.get("DB_HOST") or "127.0.0.1",
        port=int(os.environ.get("DB_PORT") or env.get("DB_PORT") or "3308"),
        user=os.environ.get("DB_USER") or env.get("DB_USER") or "n8nuser",
        password=os.environ.get("DB_PASS") or env.get("DB_PASS") or "",
        database=os.environ.get("DB_NAME") or env.get("DB_NAME") or "radio",
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10)


def ensure_schema(conn):
    with conn.cursor() as cur:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS program_settings (
               id INT NOT NULL AUTO_INCREMENT,
               program_id INT NOT NULL,
               start_mode VARCHAR(16) NOT NULL DEFAULT 'new_only',
               start_date DATE DEFAULT NULL,
               seeded TINYINT NOT NULL DEFAULT 0,
               seeded_at DATETIME DEFAULT NULL,
               last_discovery_at DATETIME DEFAULT NULL,
               discovery_note VARCHAR(255) DEFAULT NULL,
               created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
               updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                 ON UPDATE CURRENT_TIMESTAMP,
               PRIMARY KEY (id), UNIQUE KEY uq_program (program_id))""")
    conn.commit()


def existing_links(conn, pid):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT link FROM radio_program_sessions WHERE program_id=%s", (pid,))
        return {r["link"] for r in cur.fetchall()}


def main():
    try:
        pages = int(os.environ.get("NEW_SCAN_PAGES") or
                    load_env().get("NEW_SCAN_PAGES") or 14)
    except ValueError:
        pages = 14

    conn = db_conn()
    total_new = 0
    t0 = time.time()
    try:
        ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, url FROM radio_programs "
                "WHERE url IS NOT NULL AND url != '' AND is_legacy=0")
            progs = cur.fetchall()
    except Exception as e:  # noqa: BLE001
        print(f"discover: FAILED to read programs: {e}")
        return 1

    for p in progs:
        mm = re.search(r"[&?]m=(\d+)", p["url"])
        mc = re.search(r"[&?]ch=(\d+)", p["url"])
        if not mm or not mc:
            continue
        m, ch = int(mm.group(1)), int(mc.group(1))
        pid = p["id"]
        try:
            known = existing_links(conn, pid)

            inserted = 0
            for pg in range(1, pages + 1):
                try:
                    html = site.http_get(site._page_url(m, ch, pg))
                except Exception:  # noqa: BLE001
                    break
                items = site.parse_episode_cards(html)
                if not items:
                    break
                new_items = [it for it in items if it["url"] not in known]
                if new_items:
                    with conn.cursor() as cur:
                        cur.executemany(
                            "INSERT IGNORE INTO radio_program_sessions "
                            "(program_id, link, status) "
                            "VALUES (%s,%s,'pending_download')",
                            [(pid, it["url"]) for it in new_items])
                        for it in new_items:
                            known.add(it["url"])
                        inserted += len(new_items)
                    conn.commit()
                # stop when we hit a page with nothing new (we've caught up)
                if not new_items:
                    break
            total_new += inserted
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO program_settings (program_id, start_mode) "
                    "VALUES (%s,'new_only') ON DUPLICATE KEY UPDATE "
                    "last_discovery_at=NOW(), discovery_note=%s",
                    (pid, "periodic: %d new episodes" % inserted))
            conn.commit()
            print(f"discover: {p['url'][:60]} -> {inserted} new "
                  f"(known {len(known)})")
        except Exception as e:  # noqa: BLE001
            print(f"discover: program {pid} failed: {e}")
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass

    print(f"discover: DONE in {time.time()-t0:.0f}s — {total_new} new episodes "
          f"across {len(progs)} programs (pages/program={pages})")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
