"""Live link-validation CLI (Stage 2, Task C).

Bounded, polite, read-only validation of the 4 IranSeda link types over a
sample of real sessions (no secrets in the output).

Usage (from the repo root)::

    python -m corpus.validate_links \
        --sample _work/stage2_db_sample.json \
        --out reports/corpus/stage2_link_validation.json \
        --timeout 15 --delay 1.0 --max-requests 400

Synthetic mission links (e.g. an episode whose e= is absent from the DB)::

    python -m corpus.validate_links \
        --episode 14 154148409 \
        --day-archive 14 2026-11-05 \
        --out reports/corpus/stage2_link_validation.json

Rules: sequential requests, >= --delay seconds between HTTP calls, hard
--max-requests budget, resumable (skips URLs already present in --out).
The output is a per-URL result file + per-link-type coverage stats; it
never extrapolates to the full corpus.
"""

import argparse
import json
import os
import re
import sys
import time

try:  # stdlib-only console safety on Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from corpus import __version__, linkage


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def session_links(s, site_base=None):
    """All 4 link types for one session dict (R8: derived, deterministic).

    Returns a list of (link_type, url, reason_or_None). A None reason means
    the URL is eligible; a string explains why it is skipped (never
    fabricated).
    """
    ch = s.get("ch")
    e = str(s.get("e", "")).strip()
    out = []

    ep = None
    if ch is not None and e:
        ep = linkage.build_episode_url(ch, e, site_base)
    out.append((linkage.LINK_EPISODE, ep,
                None if ep else "missing ch or e"))

    cd = linkage.classify_date(s)
    gdate = (cd.get("gregorian") or {}).get("date")
    day = None
    if ch is None:
        out.append((linkage.LINK_DAY_ARCHIVE, None, "missing ch"))
    elif cd["status"] == linkage.DATE_STATUS_IMPOSSIBLE:
        out.append((linkage.LINK_DAY_ARCHIVE, None,
                    "impossible date: " + ",".join(cd["reasons"])))
    elif cd["status"] in (linkage.DATE_STATUS_CONFIRMED,
                          linkage.DATE_STATUS_UNVERIFIED) and gdate:
        day = linkage.build_day_archive_url(ch, gdate, site_base)
        out.append((linkage.LINK_DAY_ARCHIVE, day, None))
    else:
        out.append((linkage.LINK_DAY_ARCHIVE, None,
                    "date unresolvable (status=%s)" % cd["status"]))

    timeslot = None
    if day is not None:
        btime = (cd.get("jalali") or {}).get("time") or s.get("start_time")
        if btime and re_hhmm_ok(btime):
            timeslot = linkage.build_time_slot_url(ch, btime, gdate, site_base)
            out.append((linkage.LINK_TIME_SLOT, timeslot, None))
        else:
            out.append((linkage.LINK_TIME_SLOT, None, "start time unknown"))
    else:
        out.append((linkage.LINK_TIME_SLOT, None, "day archive ineligible"))

    prog = None
    purl = (s.get("program_url") or "").strip()
    if purl:
        prog = linkage.build_program_page_url(
            {"url": purl, "m": s.get("m")}, site_base)
        out.append((linkage.LINK_PROGRAM, prog["raw"], None))
    else:
        out.append((linkage.LINK_PROGRAM, None, "program_url empty"))

    return out


def re_hhmm_ok(t):
    return re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", str(t)) is not None


def _program_for(s):
    m = None
    pu = (s.get("program_url") or "")
    mm = re.search(r"[?&]m=([^&]+)", pu)
    if mm:
        m = mm.group(1)
    return {
        "id": s.get("program_id"),
        "name": s.get("program_name"),
        "url": s.get("program_url"),
        "m": m,
    }


def _session_for(s):
    return {
        "id": s.get("id"),
        "ch": s.get("ch"),
        "e": s.get("e"),
        "filename": s.get("filename"),
        "program_name": s.get("program_name"),
        "program_id": s.get("program_id"),
    }


def build_plan(sessions, extras, site_base=None):
    """Plan = ordered list of (link_type, url, session, program, source).

    Deduplicated by URL (first occurrence wins); synthetic extras first.
    """
    plan, seen = [], set()

    def add(lt, url, s, p, source):
        if not url or url in seen:
            return
        seen.add(url)
        plan.append({"link_type": lt, "url": url,
                     "session": _session_for(s) if s else None,
                     "program": _program_for(s) if s else p,
                     "source": source})

    for x in extras:
        if x["kind"] == "episode":
            add(linkage.LINK_EPISODE,
                linkage.build_episode_url(x["ch"], x["e"], site_base),
                x.get("session"), x.get("program"), "synthetic:" + x.get("label", "episode"))
        elif x["kind"] == "day_archive":
            add(linkage.LINK_DAY_ARCHIVE,
                linkage.build_day_archive_url(x["ch"], x["gregorian"], site_base),
                x.get("session"), None, "synthetic:" + x.get("label", "day_archive"))
        elif x["kind"] == "time_slot":
            add(linkage.LINK_TIME_SLOT,
                linkage.build_time_slot_url(x["ch"], x["time"], x["gregorian"], site_base),
                x.get("session"), None, "synthetic:" + x.get("label", "time_slot"))
        elif x["kind"] == "program":
            add(linkage.LINK_PROGRAM, x["url"], x.get("session"),
                {"name": x.get("name"), "m": x.get("m"), "url": x["url"]},
                "synthetic:" + x.get("label", "program"))

    for s in sessions:
        for lt, url, why in session_links(s, site_base):
            add(lt, url, s, _program_for(s),
                "session:%s" % s.get("id") if s.get("id") is not None else "session")
    return plan


def _merge_existing(out_path):
    """Resumability: keep prior per-URL results (same sample, re-run)."""
    prior = {}
    if out_path and os.path.exists(out_path):
        try:
            doc = _load_json(out_path)
            for r in doc.get("results", []):
                prior[r["url"]] = r
        except (OSError, ValueError, KeyError):
            prior = {}
    return prior


def _stats(results, plan):
    by_type = {}
    for lt in linkage.LINK_TYPES:
        by_type[lt] = {"planned": 0, "verified": 0,
                       "valid": 0, "invalid": 0, "unverified": 0,
                       "reasons": {}, "warnings": {}}
    for p in plan:
        by_type[p["link_type"]]["planned"] += 1
    for r in results:
        st = by_type.get(r["link_type"])
        if st:
            st["verified"] += 1
            st[r["status"]] += 1
            if r.get("reason"):
                st["reasons"][r["reason"]] = st["reasons"].get(r["reason"], 0) + 1
            for w in r.get("warnings") or []:
                st["warnings"][w] = st["warnings"].get(w, 0) + 1
    return by_type


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", help="sample JSON (stage2_db_sample.json shape)")
    ap.add_argument("--out", required=True, help="output JSON path")
    ap.add_argument("--timeout", type=float, default=15.0,
                    help="per-request timeout seconds (mission cap 15)")
    ap.add_argument("--delay", type=float, default=1.0,
                    help="polite delay between HTTP requests (seconds)")
    ap.add_argument("--max-requests", type=int, default=400,
                    help="hard budget for NEW http requests this run")
    ap.add_argument("--site-base", default=None,
                    help="override site base (default corpus.SITE_BASE)")
    ap.add_argument("--episode", nargs=2, metavar=("CH", "E"),
                    action="append",
                    help="synthetic episode link (repeatable)")
    ap.add_argument("--day-archive", nargs=2, metavar=("CH", "YYYY-MM-DD"),
                    action="append",
                    help="synthetic day-archive link (repeatable)")
    ap.add_argument("--time-slot", nargs=3, metavar=("CH", "HH:MM", "YYYY-MM-DD"),
                    action="append",
                    help="synthetic time-slot link (repeatable)")
    args = ap.parse_args(argv)

    if args.timeout > 15.0:
        print("WARNING: --timeout capped to 15s per mission constraint", file=sys.stderr)
        args.timeout = 15.0
    site_base = args.site_base

    sessions = []
    if args.sample:
        doc = _load_json(args.sample)
        sessions = doc.get("samples", [])
        print("loaded %d sessions from %s" % (len(sessions), args.sample))

    extras = []
    for ch, e in (args.episode or []):
        extras.append({"kind": "episode", "ch": int(ch), "e": str(e),
                       "label": "mission-episode-e%s" % e,
                       "session": {"ch": int(ch), "e": str(e),
                                   "filename": None, "id": None},
                       "program": None})
    for ch, gd in (args.day_archive or []):
        extras.append({"kind": "day_archive", "ch": int(ch), "gregorian": gd,
                       "label": "mission-day-" + gd,
                       "session": {"ch": int(ch), "filename": None, "id": None}})
    for ch, ti, gd in (args.time_slot or []):
        extras.append({"kind": "time_slot", "ch": int(ch), "time": ti,
                       "gregorian": gd, "label": "mission-timeslot-%s-%s" % (ti, gd),
                       "session": {"ch": int(ch), "filename": None,
                                   "start_time": ti, "id": None}})

    plan = build_plan(sessions, extras, site_base)
    prior = _merge_existing(args.out)

    fresh = [p for p in plan if p["url"] not in prior]
    print("plan: %d unique URLs (%d reused from prior output)"
          % (len(plan), len(plan) - len(fresh)))

    results = dict(prior)
    budget = args.max_requests
    skipped_budget = 0
    t_start = time.time()
    for i, p in enumerate(fresh, 1):
        if budget <= 0:
            skipped_budget += 1
            continue
        budget -= 1
        r = linkage.validate_link(
            p["url"],
            session=p["session"],
            program=p["program"],
            link_type=p["link_type"],
            timeout=args.timeout,
            site_base=site_base,
        )
        r["source"] = p["source"]
        r["session_id"] = p["session"].get("id") if p.get("session") else None
        results[p["url"]] = r
        if args.delay > 0:
            time.sleep(args.delay)
        print("[%d/%d] %-13s %s %s %s" % (
            i, len(fresh), r["status"].upper(), r["reason"] or "-",
            r["http_status"] if r["http_status"] is not None else "-", p["url"]))

    if skipped_budget:
        print("WARNING: %d planned URLs skipped (max-requests budget exhausted)"
              % skipped_budget, file=sys.stderr)

    # Annotate plan coverage: which URLs were eligible but never requested.
    plan_out = []
    for p in plan:
        r = results.get(p["url"])
        plan_out.append({
            "link_type": p["link_type"],
            "url": p["url"],
            "source": p["source"],
            "session_id": p["session"].get("id") if p.get("session") else None,
            "validated": bool(r),
            "status": r["status"] if r else None,
            "reason": r.get("reason") if r else "not_requested",
        })

    out = {
        "run": {
            "module": "corpus.validate_links",
            "corpus_version": __version__,
            "site_base": site_base or "https://radio.iranseda.ir/",
            "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t_start)),
            "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_s": round(time.time() - t_start, 1),
            "timeout_s": args.timeout,
            "delay_s": args.delay,
            "max_requests": args.max_requests,
            "new_requests": len(fresh) - skipped_budget,
            "skipped_budget": skipped_budget,
            "reused_from_prior": len(prior),
            "sample_file": args.sample,
            "note": ("Bounded Stage 2 validation over a stratified sample of "
                     "35 real sessions + synthetic mission links. No secrets. "
                     "Results are per-URL; do NOT extrapolate to the full "
                     "10,886-session corpus."),
        },
        "coverage_by_link_type": _stats(list(results.values()), plan),
        "plan": plan_out,
        "results": [results[p["url"]] for p in plan if p["url"] in results],
        "skipped_plan": [p for p in plan if p["url"] not in results],
    }

    d = os.path.dirname(os.path.abspath(args.out))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("wrote %s (%d results)" % (args.out, len(out["results"])))
    for lt, st in out["coverage_by_link_type"].items():
        print("  %-13s planned=%-3d verified=%-3d valid=%-3d invalid=%-3d "
              "unverified=%-3d reasons=%s" % (
                  lt, st["planned"], st["verified"], st["valid"], st["invalid"],
                  st["unverified"], st["reasons"] or "-"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
