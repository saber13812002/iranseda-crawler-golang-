"""CLI for the corpus exporter.

Usage (from the project root; the dashboard venv on 53 has pymysql):

  python -m corpus.cli check                 # connectivity + inventory
  python -m corpus.cli export [--limit N]    # full (or bounded) export
  python -m corpus.cli incremental           # watermark-based partial export
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


def cmd_export(cfg, limit=None):
    with _database.Database(cfg) as db:
        ex = _exporter.Exporter(db, cfg, log=print)
        manifest = ex.run(limit=limit)
        _metrics.write_prometheus(cfg)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


def cmd_incremental(cfg, force_full=False):
    with _database.Database(cfg) as db:
        ex = _exporter.Exporter(db, cfg, log=print)
        inc = _incremental.IncrementalExporter(ex)
        manifest = inc.run(force_full=force_full)
        _metrics.write_prometheus(cfg)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
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
        return cmd_export(cfg, limit=limit)
    if cmd == "incremental":
        return cmd_incremental(cfg, force_full="--full" in argv)
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
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
