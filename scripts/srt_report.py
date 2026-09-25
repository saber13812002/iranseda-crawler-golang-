#!/usr/bin/env python3
"""
srt_report.py — cross-references DB sessions vs actual .srt/.txt files.

Shows per program: total sessions, downloaded, has SRT, has TXT,
and "dl-no-srt" = downloaded but no SRT yet (i.e. queued for whisper).
"""
import glob
import os
import sys
from collections import defaultdict

import pymysql

conn = pymysql.connect(
    host="127.0.0.1", port=3308, user="n8nuser",
    password="StrongPassword123!", database="radio",
    charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
)
cur = conn.cursor()
cur.execute(
    """
    SELECT p.name AS pname, s.id AS sid, s.filename, s.is_downloaded
    FROM radio_program_sessions s
    JOIN radio_programs p ON p.id = s.program_id
    WHERE IFNULL(p.is_legacy, 0) = 0
    """
)
rows = cur.fetchall()
conn.close()

dl_dir = sys.argv[1] if len(sys.argv) > 1 else "downloads"
srt_names = {os.path.splitext(os.path.basename(f))[0] for f in glob.glob(dl_dir + "/*.srt")}
txt_names = {os.path.splitext(os.path.basename(f))[0] for f in glob.glob(dl_dir + "/*.txt")}

stats = defaultdict(lambda: dict(total=0, downloaded=0, has_srt=0, has_txt=0, dl_no_srt=0))
for r in rows:
    st = stats[r["pname"]]
    st["total"] += 1
    base = os.path.splitext(os.path.basename(r["filename"]))[0] if r["filename"] else None
    if base in srt_names:
        st["has_srt"] += 1
    if base in txt_names:
        st["has_txt"] += 1
    if r["is_downloaded"]:
        st["downloaded"] += 1
        if not (base and base in srt_names):
            st["dl_no_srt"] += 1

tot = dict(total=0, downloaded=0, has_srt=0, has_txt=0, dl_no_srt=0)
hdr = "%-42s %6s %5s %5s %5s %9s"
print(hdr % ("program", "total", "dl", "srt", "txt", "dl-no-srt"))
for pname, st in sorted(stats.items()):
    for k in tot:
        tot[k] += st[k]
    print(hdr % (pname[:42], st["total"], st["downloaded"], st["has_srt"], st["has_txt"], st["dl_no_srt"]))
print("-" * 86)
print(hdr % ("TOTAL", tot["total"], tot["downloaded"], tot["has_srt"], tot["has_txt"], tot["dl_no_srt"]))
