#!/usr/bin/env python3
"""
seed_session_status.py — one-time backfill of the pipeline status column.

- srt exists in downloads/           -> subtitled (is_subtitled=1)
- downloaded (mp4 on disk) no srt    -> pending_transcribe
- not downloaded                     -> pending_download
"""
import glob
import os

import pymysql

conn = pymysql.connect(
    host="127.0.0.1", port=3308, user="n8nuser",
    password="StrongPassword123!", database="radio",
    charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
)
cur = conn.cursor()
cur.execute("SELECT id, filename, is_downloaded FROM radio_program_sessions")
rows = cur.fetchall()

srt_disk = {os.path.splitext(os.path.basename(f))[0]
            for f in glob.glob("downloads/*.srt")}

ids_subtitled, ids_transcribe, ids_pend_dl = [], [], []
for r in rows:
    base = os.path.splitext(os.path.basename(r["filename"]))[0] if r["filename"] else None
    if base in srt_disk:
        ids_subtitled.append(r["id"])
    elif r["is_downloaded"]:
        ids_transcribe.append(r["id"])
    else:
        ids_pend_dl.append(r["id"])


def bulk(ids, sql):
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        placeholders = ",".join(["%s"] * len(chunk))
        cur.execute(
            "UPDATE radio_program_sessions SET %s WHERE id IN (%s)" % (sql, placeholders),
            chunk,
        )


bulk(ids_subtitled, 'status="subtitled", is_subtitled=1')
bulk(ids_transcribe, 'status="pending_transcribe"')
bulk(ids_pend_dl, 'status="pending_download"')
conn.commit()

cur.execute("SELECT status, COUNT(*) n FROM radio_program_sessions GROUP BY status ORDER BY n DESC")
for row in cur.fetchall():
    print("%-20s %d" % (row["status"], row["n"]))
conn.close()
