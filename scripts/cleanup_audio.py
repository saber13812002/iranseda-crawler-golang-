#!/usr/bin/env python3
"""
cleanup_audio.py - delete audio media for sessions subtitled more than N days ago.

Runs inside the repo (uses config.py for DB creds + downloads path, exactly like
generate_site.py), so it can be invoked by refresh_site.sh with the same env:
    ENVIRONMENT=server DB_HOST=172.20.1.53 DB_PORT=3308 \
    DOWNLOADS_PATH=.../downloads ... python3 scripts/cleanup_audio.py [--apply]

Safety rules:
  * Only deletes files whose corresponding session is in status='subtitled'
    (i.e. the SRT is already delivered). Never touches pending/in-flight media.
  * Uses the DB's `updated_at` (reliable) as the age reference, NOT file mtime
    (mtimes in downloads/ were reset once and are not trustworthy).
  * Dry-run by default: it prints what it WOULD delete. Pass --apply to delete.

Env:
  AUDIO_RETENTION_DAYS  days to keep audio after a session is subtitled (default 10)
"""
import os
import glob
import sys
import datetime

# config.py lives at the repo root (parent of scripts/); make it importable.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from config import get_config

config = get_config()
DB_HOST = config.db_config["host"]
DB_PORT = config.db_config["port"]
DB_USER = config.db_config["user"]
DB_PASS = config.db_config["password"]
DB_NAME = config.db_config["database"]
DOWNLOADS = str(config.paths["downloads"])

RETENTION_DAYS = int(os.getenv("AUDIO_RETENTION_DAYS", "10"))
APPLY = "--apply" in sys.argv
AUDIO_EXTS = (".mp3", ".mp4", ".wav", ".m4a", ".ogg")

import pymysql


def db_conn():
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS,
        database=DB_NAME, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
    )


def main():
    conn = db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT filename, updated_at FROM radio_program_sessions
                   WHERE status = 'subtitled' AND filename IS NOT NULL AND filename <> ''"""
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    now = datetime.datetime.now()
    cutoff = now - datetime.timedelta(days=RETENTION_DAYS)

    # file basename (stem) -> most recent subtitled time
    subtled_by_stem = {}
    for r in rows:
        stem = os.path.splitext(os.path.basename(r["filename"]))[0]
        t = r["updated_at"]
        if stem and t is not None:
            prev = subtled_by_stem.get(stem)
            if prev is None or t > prev:
                subtled_by_stem[stem] = t

    to_delete = []
    kept_ineligible = 0
    kept_recent = 0
    total = 0
    for path in glob.glob(os.path.join(DOWNLOADS, "*")):
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(path)[1].lower()
        if ext not in AUDIO_EXTS:
            continue
        total += 1
        stem = os.path.splitext(os.path.basename(path))[0]
        subtled_at = subtled_by_stem.get(stem)
        if subtled_at is None:
            # No subtitled session for this media -> not eligible (could be
            # pending_download / pending_transcribe / a download to transcribe).
            kept_ineligible += 1
            continue
        if subtled_at > cutoff:
            kept_recent += 1
            continue
        to_delete.append(path)

    total_bytes = sum(os.path.getsize(f) for f in to_delete)
    print("AUDIO RETENTION CLEANUP  retention=%d days  mode=%s" % (RETENTION_DAYS, "APPLY" if APPLY else "DRY-RUN"))
    print("  downloads dir:                  %s" % DOWNLOADS)
    print("  audio files scanned:            %d" % total)
    print("  kept (not subtitled / no match): %d" % kept_ineligible)
    print("  kept (subtitled < %dd ago):      %d" % (RETENTION_DAYS, kept_recent))
    print("  to delete (subtitled >= %dd ago):%d  (~%.2f GB)" % (RETENTION_DAYS, len(to_delete), total_bytes / 1e9))
    for f in sorted(to_delete)[:20]:
        print("    - " + os.path.basename(f))
    if len(to_delete) > 20:
        print("    ... and %d more" % (len(to_delete) - 20))

    if not APPLY:
        print("\nDRY-RUN: nothing deleted. Re-run with --apply to delete the %d file(s) above." % len(to_delete))
        return

    removed = 0
    for f in to_delete:
        try:
            os.remove(f)
            removed += 1
        except OSError as e:
            print("  failed to delete %s: %s" % (f, e))
    print("\nAPPLIED: deleted %d file(s), freed ~%.2f GB." % (removed, total_bytes / 1e9))


if __name__ == "__main__":
    main()
