"""Asset registry + 5-way verification CLI (Stage 3, Task C).

Builds the spec-5 asset registry for a bounded sample of sessions and runs
the 5-way verification:

  1. on disk          (downloads tree, read-only stat/sha256)
  2. asset-branch git (git cat-file -e / git log, origin/<GITHUB_BRANCH>)
  3. operational git  (same, on the checked-out operational branch - OQ-6)
  4. GitHub raw HTTP  (bounded: hard request budget, <=2 concurrent, <=15s)
  5. SHA-256 parity   (local file vs downloaded body)

Read-only, no production side effects: SELECTs only (corpus.database
refuses anything else), read-only git, no deploys, no re-export.

GitHub identity (OQ-4/R7): user/repo/branch come from the environment with
the repo .env as fallback (GITHUB_USER / GITHUB_REPO / GITHUB_BRANCH).
A missing branch ABORTS (exit 2) - the branch is never hardcoded here.

Usage (on 53, from the stage3 worktree):

    python -m corpus.scan_assets \
        --root /home/saber/saberprojects/iranseda-crawler-golang- \
        --repo /home/saber/saberprojects/iranseda-crawler-golang- \
        --downloads-dir /home/saber/saberprojects/iranseda-crawler-golang-/downloads \
        --out /tmp/saber_stage3_wt/reports/corpus/stage3_asset_verification.json \
        --stratified 24 \
        --session-ids 12345,23456 \
        --stem-prefixes radio-maaref-05-07-19-13-30,radio-maaref-05-03-10-05-30 \
        --timeout 15 --max-requests 300 --workers 2

Sample selection (any combination; empty = nothing selected):
  --session-ids    comma list of radio_program_sessions.id
  --stem-prefixes  comma list of filename prefixes (mission A/B stems)
  --stratified N   N sessions spread evenly over the id range (>=5 programs
                   guaranteed) - the Task C stratified sample
Output: a report-ready JSON (no secrets): run metadata, git-tree counts,
HTTP budget stats, per-asset-type summary, and the per-session 5-way rows.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

try:  # stdlib-only console safety on Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from corpus import __version__, assets
from corpus.config import Config, load_dotenv


def _utcnow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# config / git

def parse_github_remote(url):
    """(user, repo) from a GitHub remote URL, or (None, None).

    Accepts https and ssh forms, with or without trailing .git."""
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$",
                  (url or "").strip())
    if not m:
        return None, None
    return m.group(1), m.group(2)


def load_github(root, repo):
    """GitHub identity for asset URLs (OQ-4 / R7).

    user/repo: parsed from `git remote get-url origin` (the real remote —
    never hardcoded), with GITHUB_USER/GITHUB_REPO env as fallback.
    branch: GITHUB_BRANCH from env, then <root>/.env — the ONLY source
    (spec C4: never hardcoded; abort when missing).
    """
    env_file = load_dotenv(os.path.join(root, ".env"))

    def pick(k):
        v = os.environ.get(k)
        if v is None or v == "":
            v = env_file.get(k)
        return (v or "").strip() or None

    user = repo_name = None
    rc, out, _err = git_out(repo, ["remote", "get-url", "origin"])
    if rc == 0:
        user, repo_name = parse_github_remote(out)
    return {"user": user or pick("GITHUB_USER"),
            "repo": repo_name or pick("GITHUB_REPO"),
            "branch": pick("GITHUB_BRANCH")}


def git_out(repo, args, timeout=180):
    try:
        p = subprocess.run(["git", "-C", repo] + list(args),
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout or "", p.stderr or ""
    except Exception as e:
        return 1, "", "%s: %s" % (type(e).__name__, e)


# ---------------------------------------------------------------------------
# DB (read-only)

def _parse_ids(s):
    out = []
    for tok in (s or "").split(","):
        tok = tok.strip()
        if tok.isdigit():
            out.append(int(tok))
    return out


def _parse_prefixes(s):
    return [t.strip() for t in (s or "").split(",") if t.strip()]


def stratified_pick(db, n):
    """Deterministic stratified sample: n ids spread evenly over the id
    range (id order ~ insertion ~ chronological), with >=5 programs."""
    rows = db.query("SELECT id, program_id FROM radio_program_sessions "
                    "ORDER BY id")
    if not rows:
        return []
    n = max(2, int(n))
    if len(rows) <= n:
        return [r["id"] for r in rows]
    idxs = [int(round(i * (len(rows) - 1) / float(n - 1)))
            for i in range(n)]
    picks = [rows[i]["id"] for i in idxs]
    progs = {rows[i]["program_id"] for i in idxs}
    if len(progs) < 5:
        for r in rows:
            if len(progs) >= 5:
                break
            if r["id"] in picks:
                continue
            picks.append(r["id"])
            progs.add(r["program_id"])
    return sorted(set(picks))


def fetch_sessions(db, ids, prefixes, limit):
    # ids + prefixes form a UNION (OR): explicit picks and stem matches
    # are separate selection criteria, not a conjunction
    conds, params = [], []
    if ids:
        conds.append("id IN (%s)" % ",".join(["%s"] * len(ids)))
        params.extend(int(i) for i in ids)
    for p in prefixes:
        conds.append("(filename LIKE %s OR srt_filename LIKE %s)")
        params.append(p + "%")
        params.append(p + "%")
    where = " OR ".join(conds) if conds else "1=1"
    sql = ("SELECT %s FROM radio_program_sessions WHERE %s "
           "ORDER BY id LIMIT %d" % (db.SESSIONS_COLS, where, int(limit)))
    return db.query(sql, tuple(params))


def fetch_llm(db, session_ids):
    sids = sorted({int(i) for i in session_ids if i})
    if not sids:
        return []
    sql = ("SELECT id, session_id, job_type, model, file_relpath, "
           "finished_at, status FROM llm_output "
           "WHERE session_id IN (%s) ORDER BY id"
           % ",".join(["%s"] * len(sids)))
    return db.query(sql, tuple(sids))


def quarantine_ids(out_dir):
    """record_id set from <out_dir>/quarantine.jsonl (spec 10.1)."""
    ids = set()
    p = os.path.join(out_dir, "quarantine.jsonl")
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rid = json.loads(line).get("record_id")
                except ValueError:
                    continue
                if rid:
                    ids.add(rid)
    except OSError:
        pass
    return ids


# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=None,
                    help="corpus project root (default: parent of corpus/)")
    ap.add_argument("--repo", default=None,
                    help="git repo dir for cat-file/log (default: root)")
    ap.add_argument("--downloads-dir", default=None,
                    help="base dir for asset relpaths (default: <root>; "
                         "asset relpaths start with downloads/, so the base "
                         "is the repo/project root, not the downloads tree)")
    ap.add_argument("--out", default=None,
                    help="output JSON (default: <root>/reports/corpus/"
                         "stage3_asset_verification.json)")
    ap.add_argument("--cache", default=None,
                    help="HTTP cache JSON for resumability (default: <out>.http_cache.json)")
    ap.add_argument("--session-ids", default="",
                    help="comma list of radio_program_sessions.id")
    ap.add_argument("--stem-prefixes", default="",
                    help="comma list of filename/srt prefixes")
    ap.add_argument("--stratified", type=int, default=0, metavar="N",
                    help="add N evenly-spread stratified sessions (>=5 programs)")
    ap.add_argument("--limit", type=int, default=500,
                    help="max sessions to load (default 500)")
    ap.add_argument("--timeout", type=float, default=15.0,
                    help="per-request HTTP timeout, capped at 15s (default 15)")
    ap.add_argument("--max-requests", type=int, default=300,
                    help="hard HTTP budget for this run (default 300)")
    ap.add_argument("--workers", type=int, default=2,
                    help="HTTP concurrency, capped at 2 (default 2)")
    ap.add_argument("--verify-statuses", default="",
                    help="comma list of C11 statuses to HTTP-probe "
                         "(default: all entries)")
    ap.add_argument("--operational-branch", default=None,
                    help="operational branch for OQ-6 (default: current branch)")
    ap.add_argument("--no-http", action="store_true",
                    help="skip ways 4+5 (offline runs)")
    ap.add_argument("--no-git-fetch", action="store_true",
                    help="skip the read-only `git fetch origin` pre-pass")
    args = ap.parse_args(argv)

    t0 = time.time()
    started = _utcnow()
    root = args.root or os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    repo = args.repo or root
    # asset relpaths are root-relative (downloads/..., downloads/cleaned/...)
    downloads = args.downloads_dir or root
    out = args.out or os.path.join(root, "reports", "corpus",
                                   "stage3_asset_verification.json")
    cache = args.cache or (out + ".http_cache.json")

    # -- github identity (R7: from the real git remote + config; abort if
    #    the branch is missing instead of hardcoding)
    gh = load_github(root, repo)
    missing = [k for k in ("user", "repo", "branch") if not gh.get(k)]
    if missing:
        print("ERROR: missing GitHub config: %s" % ",".join(
            "GITHUB_" + k.upper() for k in missing))
        print("R7: the asset branch must come from production config/env; "
              "aborting instead of hardcoding.")
        return 2

    timeout = min(15.0, max(1.0, args.timeout))
    workers = min(2, max(1, args.workers))

    # -- operational branch (OQ-6): default = the checked-out branch
    op_branch = args.operational_branch
    if op_branch is None:
        rc, o, _e = git_out(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
        op_branch = o.strip() if rc == 0 else None
    if op_branch == "HEAD":
        op_branch = None

    # -- read-only git fetch (refreshes origin refs only)
    fetch_rc, fetch_out, fetch_err = 0, "", ""
    if not args.no_git_fetch:
        fetch_rc, fetch_out, fetch_err = git_out(repo, ["fetch", "origin",
                                                        "--quiet"])
    head_sha, head_err = None, ""
    rc, o, e = git_out(repo, ["rev-parse", "HEAD"])
    if rc == 0:
        head_sha = o.strip()
    else:
        head_err = e.strip()

    # -- DB (read-only)
    from corpus import database
    cfg = Config.from_env(root=root)
    db = database.Database(cfg)
    db.connect()
    try:
        ids = _parse_ids(args.session_ids)
        prefixes = _parse_prefixes(args.stem_prefixes)
        strat_ids = []
        if args.stratified > 0:
            # union of explicit picks + stratified spread (deterministic)
            strat_ids = stratified_pick(db, args.stratified)
            ids = sorted(set(ids) | set(strat_ids))
        if not ids and not prefixes:
            print("ERROR: no sessions selected (pass --session-ids, "
                  "--stem-prefixes and/or --stratified N)")
            return 2
        sessions = fetch_sessions(db, ids, prefixes, args.limit)
        sids = [int(s["id"]) for s in sessions]
        llm = fetch_llm(db, sids)
        qids = quarantine_ids(cfg.out_dir)
    finally:
        db.close()

    # -- registry + ways 1-3
    registry = assets.build_registry(sessions, llm, gh,
                                     operational_branch=op_branch,
                                     quarantine_ids=qids)
    # cap local sha256 at the download cap: files above it get a head/tail
    # fingerprint, so way 5 verifies them with a bounded 2-Range probe
    on_disk = assets.check_disk(registry, downloads,
                                sha_cap_bytes=assets.DEFAULT_SHA_CAP)
    # git refs: the asset branch normally exists only as origin/<branch>
    # after fetch; the operational branch is the checked-out local branch
    asset_ref = "origin/" + gh["branch"]
    if op_branch and op_branch == gh["branch"]:
        op_ref = asset_ref
    else:
        op_ref = op_branch
    gitres = assets.check_git_tree(registry, repo, asset_ref,
                                   operational_ref=op_ref)

    # -- ways 4-5
    vs = set(t.strip() for t in args.verify_statuses.split(",")
             if t.strip()) or None
    http_stats = None
    if not args.no_http:
        http_stats = assets.verify_http(
            registry, timeout=timeout, max_requests=args.max_requests,
            max_workers=workers, cache_path=cache, verify_statuses=vs)

    summary = assets.summarize(registry)
    result = {
        "run": {
            "module": "corpus.scan_assets",
            "corpus_version": __version__,
            "started_at_utc": started,
            "finished_at_utc": _utcnow(),
            "duration_s": round(time.time() - t0, 1),
            "root": root,
            "repo_head_sha": head_sha,
            "repo_head_err": head_err or None,
            "git_fetch": {"ok": fetch_rc == 0,
                          "stderr": (fetch_err or "").strip()[:400] or None},
            "github": {"user": gh["user"], "repo": gh["repo"],
                       "branch": gh["branch"]},
            "asset_branch": gh["branch"],
            "operational_branch": op_branch,
            "asset_path_base": downloads,
            "selection": {
                "session_ids": _parse_ids(args.session_ids),
                "stem_prefixes": prefixes,
                "stratified_requested": args.stratified,
                "stratified_ids": strat_ids,
                "sessions_loaded": len(sessions),
                "limit": args.limit,
            },
            "http": {"no_http": args.no_http, "timeout_s": timeout,
                     "max_requests": args.max_requests,
                     "workers": workers,
                     "verify_statuses": sorted(vs) if vs else None},
        },
        "on_disk": on_disk,
        "git_tree": gitres,
        "http_stats": http_stats,
        "summary": summary,
        "sessions": [
            {
                "session_id": s["session_id"],
                "program_id": s["program_id"],
                "session_uid": s["session_uid"],
                "quarantined": s["quarantined"],
                "filename": s["filename"],
                "srt_filename": s["srt_filename"],
                "stem": s["stem"],
                "stem_family": s["stem_family"],
                "broadcast_jalali": s["broadcast_jalali"],
                "asset_count": s["asset_count"],
                "assets": [assets.five_way_row(s, a) for a in s["assets"]],
            }
            for s in registry
        ],
    }
    d = os.path.dirname(os.path.abspath(out))
    if d and not os.path.isdir(d):
        os.makedirs(d)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)
    os.replace(tmp, out)

    print("sessions=%d assets=%d on_disk=%d in_asset_branch=%d "
          "in_operational_branch=%d" % (
              len(registry), summary["total_assets"], on_disk,
              gitres["in_asset_branch"], gitres["in_operational_branch"]))
    if http_stats:
        print("http: 200=%d 404=%d other=%d error=%d skipped_budget=%d "
              "reused=%d sha(match=%d mismatch=%d skipped_large=%d na=%d)" % (
                  http_stats["http_200"], http_stats["http_404"],
                  http_stats["http_other"], http_stats["http_error"],
                  http_stats["skipped_budget"],
                  http_stats["reused_from_prior"],
                  http_stats["sha_match_true"],
                  http_stats["sha_match_false"],
                  http_stats["sha_skipped_large"],
                  http_stats["sha_na"]))
    print("wrote %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
