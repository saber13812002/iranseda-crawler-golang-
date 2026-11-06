"""Independent corpus scheduler (mission §9) — env-gated, low priority.

Disabled by default: CORPUS_EXPORT_ENABLED=false. When enabled it runs
an incremental export every CORPUS_INCREMENTAL_HOURS (default 6) and a
full reconcile weekly. It is a standalone process (NOT wired into
run_pipeline.sh) so it can never disturb the main pipeline:

    python -m corpus.cli schedule        # run once (cron-friendly)
    CORPUS_EXPORT_ENABLED=true python -m corpus.cli schedule --loop

Cron example (on 53, separate from the pipeline crons):
    0 */6 * * *  cd /home/saber/saberprojects/iranseda-crawler-golang- && CORPUS_EXPORT_ENABLED=true dashboard/venv/bin/python3 -m corpus.cli schedule >> data/corpus/scheduler.log 2>&1
    0 3 * * 0   cd ... && CORPUS_EXPORT_ENABLED=true dashboard/venv/bin/python3 -m corpus.cli schedule --reconcile
"""

import os
import sys
import time
import datetime

from . import config as _config
from . import database as _database
from . import exporter as _exporter
from . import incremental as _incremental
from . import metrics as _metrics

STATE_LOCK = "scheduler.lock"


def _log(msg):
    print("[%s] %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))
    sys.stdout.flush()


def _acquire_lock(cfg):
    """Single-instance guard (pidfile with stale detection).

    Uses exporter._pid_alive: on Windows os.kill(pid, 0) is NOT a
    liveness check (signal 0 == Ctrl+C event for the console group) —
    it must go through OpenProcess instead.
    """
    path = os.path.join(cfg.out_dir, STATE_LOCK)
    os.makedirs(cfg.out_dir, exist_ok=True)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                old = int(f.read().strip() or 0)
            if _exporter._pid_alive(old):
                _log("scheduler: another instance running (pid %d) — exiting" % old)
                return False
        except ValueError:
            pass  # unreadable/stale lock
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    return True


def _release_lock(cfg):
    path = os.path.join(cfg.out_dir, STATE_LOCK)
    # read the holder BEFORE removing: on Windows os.remove fails
    # (WinError 32) while the file still has an open handle.
    holder = None
    try:
        with open(path, encoding="utf-8") as f:
            holder = f.read().strip()
    except OSError:
        return
    if holder == str(os.getpid()):
        try:
            os.remove(path)
        except OSError:
            pass


def _weekly_reconcile_due(cfg):
    """True once per ISO week (checked via a state marker file)."""
    import json
    marker = os.path.join(cfg.out_dir, "last_reconcile_week.txt")
    iso = datetime.date.today().isocalendar()
    key = "%04d-W%02d" % (iso[0], iso[1])
    if os.path.exists(marker):
        with open(marker, encoding="utf-8") as f:
            if f.read().strip() == key:
                return False
    os.makedirs(cfg.out_dir, exist_ok=True)
    with open(marker, "w", encoding="utf-8") as f:
        f.write(key)
    return True


def run_cycle(cfg=None, reconcile=False, log=_log):
    """One scheduler cycle. Returns manifest (or reconcile report)."""
    cfg = cfg or _config.Config.from_env()
    if not cfg.export_enabled:
        log("scheduler: CORPUS_EXPORT_ENABLED=false — no-op")
        return None
    if not _acquire_lock(cfg):
        return None
    try:
        with _database.Database(cfg) as db:
            db.ping()
            ex = _exporter.Exporter(db, cfg, log=log)
            inc = _incremental.IncrementalExporter(ex)
            if reconcile:
                report = inc.reconcile()
                _metrics.write_prometheus(cfg)
                return report
            manifest = inc.run()
            _metrics.write_prometheus(cfg)
            return manifest
    finally:
        _release_lock(cfg)


def loop(cfg=None, log=_log):
    """Block forever, running a cycle every incremental_hours."""
    cfg = cfg or _config.Config.from_env()
    interval = max(60.0, cfg.incremental_hours * 3600.0)
    log("scheduler: loop starting (interval %.0f s, enabled=%s)"
        % (interval, cfg.export_enabled))
    while True:
        t0 = time.time()
        try:
            run_cycle(cfg, log=log)
        except Exception as e:  # noqa: BLE001 — the loop must survive
            log("scheduler: cycle failed: %r" % e)
        # weekly reconcile on a separate cadence
        try:
            if _weekly_reconcile_due(cfg):
                log("scheduler: weekly reconcile due")
                run_cycle(cfg, reconcile=True, log=log)
        except Exception as e:  # noqa: BLE001
            log("scheduler: reconcile failed: %r" % e)
        elapsed = time.time() - t0
        sleep_for = max(5.0, interval - elapsed)
        time.sleep(sleep_for)
