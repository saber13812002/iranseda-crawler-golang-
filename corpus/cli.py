"""CLI for the corpus exporter.

Usage (from the project root; the dashboard venv on 53 has pymysql):

  python -m corpus.cli check                 # connectivity + inventory
  python -m corpus.cli export [--limit N] [--deterministic] [--run-id ID]
                               # full (or bounded) export; --deterministic
                               # pins exported_at to the DB watermark;
                               # --assets adds the git ls-tree asset tier
  python -m corpus.cli incremental [--full] [--pin] [--assets]
                               # watermark-based upsert-merge; --pin pins
                               # exported_at+run_id to the live manifest
                               # (no-change merge = byte-identical no-op)
  python -m corpus.cli rag-linkage           # asset manifest + RAG linkage
  python -m corpus.cli reconcile             # full re-scan + diff report
  python -m corpus.cli validate              # validate the current output
  python -m corpus.cli publish               # build the HF local bundle
  python -m corpus.cli schedule [--loop]     # one scheduler cycle / loop
  python -m corpus.cli metrics               # recompute metrics.prom

Env-gated (mission §8): nothing here is scheduled automatically; the
scheduler no-ops unless CORPUS_EXPORT_ENABLED=true.
"""

import sys
import json

from . import config as _config
from . import database as _database
from . import exporter as _exporter
from . import incremental as _incremental
from . import validator as _validator
from . import publisher as _publisher
from . import metrics as _metrics
from . import scheduler as _scheduler
from . import identity as _identity
from .extractor import DiskIndex


def _make_db(cfg, log=print):
    db = _database.Database(cfg)
    db.connect()
    log("db: connected (%s:%s/%s)" % (cfg.db_host, cfg.db_port, cfg.db_name))
    return db


def cmd_check(cfg):
    with _database.Database(cfg) as db:
        ver = db.ping()
        counts = db.table_counts()
        wm = db.high_watermark()
    out = {"db_version": ver, "counts": counts, "watermark": wm,
           "downloads_dir": cfg.downloads_dir, "out_dir": cfg.out_dir}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def _asset_context(cfg, log=print):
    """linkage_ctx for the v1.1 asset tier: ONE ``git ls-tree -r`` set.

    The branch comes ONLY from the live GITHUB_BRANCH (env, then
    <root>/.env) — never hardcoded (R7). Missing branch or git failure:
    warn and return None (git-tree tier stays None/unknown, no abort).
    """
    from . import scan_assets as _scan
    gh = _scan.load_github(cfg.root, cfg.root)
    if not gh.get("branch"):
        log("assets: GITHUB_BRANCH not set (env or .env) — "
            "git-tree tier disabled")
        return None
    rc, out, err = _scan.git_out(cfg.root,
                                 ["ls-tree", "-r", "--name-only",
                                  gh["branch"]])
    if rc != 0:
        log("assets: git ls-tree failed (rc=%d): %s"
            % (rc, (err or "").strip()[:200]))
        return None
    paths = set(l for l in out.splitlines() if l.strip())
    log("assets: git ls-tree %s -> %d paths" % (gh["branch"], len(paths)))
    return {"git_paths": paths}


def cmd_export(cfg, limit=None, deterministic=False, run_id=None,
               assets=False):
    with _database.Database(cfg) as db:
        wm = db.high_watermark()
        # --deterministic: pin exported_at to the DB high watermark so
        # two runs over unchanged data produce byte-identical data files
        # and identical checksums.sha256 (manifest duration_sec excepted).
        exported_at = None
        if deterministic:
            anchor = (wm.get("sessions_updated_at")
                      or wm.get("llm_finished_at") or "")
            if not anchor:
                print("export: cannot pin exported_at (empty DB watermark)")
                return 2
            exported_at = anchor
            if run_id is None:
                # filesystem-safe (':') — matches Exporter's derivation
                run_id = "corpus-det-%s" % (anchor
                                             .replace(" ", "T")
                                             .replace(":", "-"))
        linkage_ctx = _asset_context(cfg) if assets else None
        ex = _exporter.Exporter(db, cfg, log=print)
        manifest = ex.run(limit=limit, run_id=run_id,
                          exported_at=exported_at,
                          linkage_ctx=linkage_ctx)
        _metrics.write_prometheus(cfg)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


def cmd_incremental(cfg, force_full=False, pin=False, assets=False):
    run_id = None
    exported_at = None
    if pin:
        # byte-identical no-op merges: pin exported_at + run_id to the
        # LIVE manifest (records carry provenance.exported_at and
        # provenance.export_version=run_id)
        import os
        mp = os.path.join(cfg.out_dir, "manifest.json")
        if os.path.exists(mp):
            with open(mp, encoding="utf-8") as f:
                lm = json.load(f)
            exported_at = lm.get("exported_at")
            run_id = lm.get("run_id")
            print("incremental: pinned exported_at=%s run_id=%s "
                  "(live manifest)" % (exported_at, run_id))
        else:
            print("incremental: --pin but no live manifest.json")
            return 2
    with _database.Database(cfg) as db:
        ex = _exporter.Exporter(db, cfg, log=print)
        inc = _incremental.IncrementalExporter(ex)
        manifest = inc.run(force_full=force_full, run_id=run_id,
                           exported_at=exported_at,
                           linkage_ctx=_asset_context(cfg) if assets else None)
        _metrics.write_prometheus(cfg)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


def cmd_rag_linkage(cfg):
    """Stage 4: asset manifest (JSONL) + RAG linkage dataset (JSONL)."""
    from . import rag_linkage as _rag_linkage
    summary = _rag_linkage.main(cfg, log=print)
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_reconcile(cfg):
    with _database.Database(cfg) as db:
        ex = _exporter.Exporter(db, cfg, log=print)
        inc = _incremental.IncrementalExporter(ex)
        report = inc.reconcile()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def cmd_validate(cfg):
    import os
    paths = []
    sp = os.path.join(cfg.out_dir, "corpus.jsonl")
    if os.path.exists(sp):
        paths.append(sp)
    else:
        for p in sorted(os.listdir(cfg.out_dir)) if os.path.isdir(cfg.out_dir) else []:
            if p.startswith("corpus-") and p.endswith(".jsonl"):
                paths.append(os.path.join(cfg.out_dir, p))
    # Stream line-by-line (a full export can be several GB; never materialize
    # all records in memory). validate_record is per-record + a shared seen set.
    seen = set()
    problems = {}
    checked = 0
    ok = 0
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                checked += 1
                probs = _validator.validate_record(rec, seen_ids=seen)
                if probs:
                    rid = rec.get("record_id") if isinstance(rec, dict) else None
                    problems[rid or "<unknown>"] = probs
                else:
                    ok += 1
    summary = {"records_checked": checked, "ok": ok,
               "invalid": len(problems), "problems": problems}
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not problems else 2


def cmd_publish(cfg):
    with _database.Database(cfg) as db:
        ex = _exporter.Exporter(db, cfg, log=print)
        pub = _publisher.Publisher(cfg, log=print)
        status = pub.prepare(None)
    print(json.dumps(status, indent=2, ensure_ascii=False))
    return 0


def cmd_investigate(cfg):
    """Stage 1: Class B identity investigation (read-only).

    Writes data/corpus/class_b_investigation.jsonl (summary line + one
    line per colliding (ch, e) group). Never modifies DB or corpus.
    """
    import os
    with _database.Database(cfg) as db:
        disk = DiskIndex(cfg.downloads_dir)
        disk.scan()
        result = _identity.investigate(db, disk=disk, log=print)
    out = os.path.join(cfg.out_dir, "class_b_investigation.jsonl")
    os.makedirs(cfg.out_dir, exist_ok=True)
    _identity.write_jsonl(result, out)
    print("investigation written to %s (%d groups)"
          % (out, result["summary"]["groups_total"]))
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False))
    return 0


def cmd_metrics(cfg):
    p = _metrics.write_prometheus(cfg)
    print("metrics written to %s" % p)
    return 0


def cmd_schedule(cfg, loop=False, reconcile=False):
    if loop:
        _scheduler.loop(cfg)
        return 0
    result = _scheduler.run_cycle(cfg, reconcile=reconcile)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]
    cfg = _config.Config.from_env()
    if cmd == "check":
        return cmd_check(cfg)
    if cmd == "export":
        limit = None
        if "--limit" in argv:
            limit = int(argv[argv.index("--limit") + 1])
        run_id = None
        if "--run-id" in argv:
            run_id = argv[argv.index("--run-id") + 1]
        return cmd_export(cfg, limit=limit,
                          deterministic="--deterministic" in argv,
                          run_id=run_id, assets="--assets" in argv)
    if cmd == "incremental":
        return cmd_incremental(cfg, force_full="--full" in argv,
                               pin="--pin" in argv,
                               assets="--assets" in argv)
    if cmd == "rag-linkage":
        return cmd_rag_linkage(cfg)
    if cmd == "reconcile":
        return cmd_reconcile(cfg)
    if cmd == "validate":
        return cmd_validate(cfg)
    if cmd == "publish":
        return cmd_publish(cfg)
    if cmd == "metrics":
        return cmd_metrics(cfg)
    if cmd == "schedule":
        return cmd_schedule(cfg, loop="--loop" in argv,
                            reconcile="--reconcile" in argv)
    if cmd == "investigate":
        return cmd_investigate(cfg)
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
