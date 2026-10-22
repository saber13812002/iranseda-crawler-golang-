#!/usr/bin/env python3
"""RADIO RAG — full read-only audit over ALL mp4+subtitled sessions.

Produces state/full_audit.json with:
  - total / distinct-stem / eligible / no-air-date counts
  - how many no-air-date are recoverable from p.time_description
  - session-identity collision stats (how many stems map to >1 session_id,
    and how many episodes are unique-by-session vs duplicate-by-stem)
  - per-artifact coverage over the whole corpus (raw srt/txt/mp4 + 5 LLM artifacts)
No writes, no modifications, no secrets.
"""
import json, os, re, subprocess, sys
from collections import Counter, defaultdict

BASE = "/home/saber/saberprojects/iranseda-crawler-golang-"
DL = os.path.join(BASE, "downloads")
CL = os.path.join(DL, "cleaned")


def q(sql: str):
    pw = os.environ.get("RADIO_DB_PASS", "")
    if not pw:
        raise SystemExit("RADIO_DB_PASS not set")
    r = subprocess.run(
        ["docker", "exec", "-i", "iranseda-mysql", "mysql", "-un8nuser",
         f"-p{pw}", "-N", "--default-character-set=utf8mb4", "--batch",
         "-e", f"USE radio; {sql}"],
        capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-400:])
    return [l for l in r.stdout.splitlines() if l]


MONTHS = {"فروردین":1,"اردیبهشت":2,"خرداد":3,"تیر":4,"مرداد":5,"شهریور":6,
          "مهر":7,"آبان":8,"آذر":9,"دی":10,"بهمن":11,"اسفند":12}


def has_time_description_date(td: str) -> bool:
    """Does p.time_description contain a parseable 'DD MonthName YYYY ساعت HH:MM'."""
    if not td:
        return False
    return bool(re.search(r"\d{1,2}\s+[ا-ی]+\s+\d{4}\s*ساعت\s*\d{1,2}:\d{2}", td))


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "state")
    os.makedirs(outdir, exist_ok=True)

    # 1. all mp4+subtitled sessions joined to radio_programs (has time_description)
    rows = q(
        "SELECT s.id, s.filename, p.time_description, p.name FROM radio_program_sessions s "
        "LEFT JOIN radio_programs p ON s.program_id=p.id "
        "WHERE s.status='subtitled' AND s.filename LIKE '%mp4%';")
    total = len(rows)

    # distinct stems
    stem2sids = defaultdict(set)      # stem -> set(session_ids)
    stem2td = {}                       # stem -> time_description (last seen)
    for line in rows:
        # a description / time_description can contain a tab -> split into
        # at most 4 fields: sid | filename | time_description | name(+)
        parts = line.split("\t")
        sid, fn = parts[0], parts[1]
        td = parts[2] if len(parts) > 2 else ""
        stem = fn
        for ext in (".mp4", ".srt", ".txt"):
            if stem.endswith(ext):
                stem = stem[:-len(ext)]
        stem2sids[stem].add(int(sid))
        if td:
            stem2td[stem] = td
    distinct = len(stem2sids)

    # 2. air-date eligibility (re-using the parse rules from extract.py, simplified)
    #    eligible if: time_description has a date OR filename parses to a valid
    #    persian month/day with a resolvable year.
    eligible, no_air, td_recoverable = 0, 0, 0
    no_air_stems = []
    for stem, sids in stem2sids.items():
        td = stem2td.get(stem, "")
        td_ok = has_time_description_date(td)
        # filename parse: radio-CH-MM-DD-HH-MM-SS (a<=12 => month) or legacy a>=13
        m = re.match(r"^radio-([\w_]+)-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})$", stem)
        fn_ok = False
        if m:
            a = int(m.group(2))
            if a <= 12:  # current format: month-day-hh-mm-ss
                mo, da = a, int(m.group(3))
                fn_ok = 1 <= mo <= 12 and 1 <= da <= 31
            # legacy (a>=13) already has a year in the name -> date resolvable
            elif a >= 13:
                fn_ok = 1 <= int(m.group(3)) <= 12 and 1 <= int(m.group(4)) <= 31
        if td_ok or fn_ok:
            eligible += 1
        else:
            no_air += 1
            no_air_stems.append(stem)
            if td_ok:  # (defensive; td_ok already counted above)
                td_recoverable += 1

    # how many no-air stems DO have a time_description date we just couldn't match
    # (i.e., recovery potential) — count those with any persian month+year in td
    td_potential = sum(1 for s in no_air_stems if has_time_description_date(stem2td.get(s, "")))

    # 3. session-identity collisions
    multi = {s: ids for s, ids in stem2sids.items() if len(ids) > 1}
    total_sessions = sum(len(v) for v in stem2sids.values())

    # 4. artifact coverage over the WHOLE corpus (file existence)
    art = Counter()
    for stem in stem2sids:
        if os.path.exists(os.path.join(DL, stem + ".srt")):
            art["raw_srt"] += 1
        if os.path.exists(os.path.join(DL, stem + ".txt")):
            art["raw_txt"] += 1
        if os.path.exists(os.path.join(DL, stem + ".mp4")):
            art["mp4"] += 1
        if os.path.exists(os.path.join(CL, stem + ".correct.srt")):
            art["correct_srt"] += 1
        if os.path.exists(os.path.join(CL, stem + ".correct.txt")):
            art["correct_txt"] += 1
        if os.path.exists(os.path.join(CL, stem + ".summary.txt")):
            art["summary_fa"] += 1
        if os.path.exists(os.path.join(CL, stem + ".summary.en.txt")):
            art["summary_en"] += 1

    # 5. correct.srt missing but raw present -> these are the "134 unprocessed"
    #    (correct.srt is what chunking needs)
    need_backfill = [s for s in stem2sids
                     if not os.path.exists(os.path.join(CL, s + ".correct.srt"))
                     and os.path.exists(os.path.join(DL, s + ".srt"))]

    report = {
        "generated_at": "2026-10-22",
        "total_sessions_mp4_subtitled": total,
        "distinct_stems": distinct,
        "total_session_rows": total_sessions,
        "eligible_air_date": eligible,
        "no_air_date": no_air,
        "no_air_with_time_description_potential": td_potential,
        "stem_collision": {
            "stems_with_multiple_sessions": len(multi),
            "extra_session_rows_from_collisions":
                sum(len(v) - 1 for v in multi.values()),
            "max_sessions_per_stem": max((len(v) for v in stem2sids.values()), default=0),
            "top_collisions": sorted(
                ({"stem": s, "session_count": len(ids),
                  "session_ids": sorted(ids)} for s, ids in multi.items()),
                key=lambda x: -x["session_count"])[:10],
        },
        "artifact_coverage_over_distinct_stems": dict(art),
        "missing_correct_srt_but_raw_present": len(need_backfill),
        "missing_correct_srt_sample": sorted(need_backfill)[:20],
        "note": ("keying on session_id (not stem) is REQUIRED for the full run: "
                 f"{len(multi)} stems map to >1 session_id; total session rows = "
                 f"{total_sessions} vs {distinct} stems."),
    }
    with open(os.path.join(outdir, "full_audit.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
