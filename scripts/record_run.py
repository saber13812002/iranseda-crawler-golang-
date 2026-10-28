#!/usr/bin/env python3
"""Record one cron run into the pipeline_runs table (radio DB, UTC).

Called from:
  scripts/run_pipeline.sh   -> kind=pipeline (scan + discover + download)
  scripts/refresh_site.sh   -> kind=site     (generate + git push)

All input arrives via REC_* environment variables. The script is
best-effort: it NEVER raises into the caller — on any error it prints
"record: FAILED: ..." and exits 0, so it can never break the pipeline.

REC_ variables:
  KIND            pipeline | site
  STARTED_AT      "YYYY-MM-DD HH:MM:SS" (server time; 53 runs UTC)
  STATUS          ok | failed
  ERROR           error summary (optional, truncated to 1000 chars)
  pipeline: SCAN_NEW DISC_NEW DISC_PROGRAMS DL_OK DL_FAIL
  site:     PUBLISHED SRT_NEW TXT_NEW PUSH_OK (0/1)

new_srt_count for kind=pipeline is computed here from the DB:
subtitled sessions whose updated_at falls inside the run window
(ASR output produced by this run's downloads, minus the worker lag).
"""
import os
import sys
import time
import uuid
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT, ".env")

CREATE_TABLE = """CREATE TABLE IF NOT EXISTS pipeline_runs (
  id INT NOT NULL AUTO_INCREMENT,
  run_id VARCHAR(72) NOT NULL,
  kind VARCHAR(16) NOT NULL COMMENT 'pipeline (scan+discover+download) | site (generate+push)',
  started_at DATETIME NOT NULL,
  finished_at DATETIME DEFAULT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'ok' COMMENT 'ok | failed',
  discovered_programs INT NOT NULL DEFAULT 0 COMMENT 'active programs walked by discover_new.py',
  discovered_sessions INT NOT NULL DEFAULT 0 COMMENT 'new episodes discovered this run (scan+discover)',
  new_sessions INT NOT NULL DEFAULT 0 COMMENT 'total new sessions this run (== discovered_sessions)',
  no_new_work TINYINT NOT NULL DEFAULT 0 COMMENT '1 = ok run with 0 new sessions (expected, NOT an error)',
  queued_downloads INT NOT NULL DEFAULT 0 COMMENT 'download attempts made this run (success+failure)',
  download_success INT NOT NULL DEFAULT 0,
  download_failure INT NOT NULL DEFAULT 0,
  asr_started INT NOT NULL DEFAULT 0,
  asr_success INT NOT NULL DEFAULT 0,
  asr_failure INT NOT NULL DEFAULT 0,
  new_srt_count INT NOT NULL DEFAULT 0 COMMENT 'SRTs produced during this run (by updated_at window)',
  new_txt_count INT NOT NULL DEFAULT 0 COMMENT 'full-text .txt files added this run (site kind)',
  published_output_count INT NOT NULL DEFAULT 0 COMMENT 'changed paths committed+pushed this run (site kind)',
  push_ok TINYINT NOT NULL DEFAULT 0 COMMENT '1 = a commit was actually pushed to the remote (site kind)',
  duration_seconds INT NOT NULL DEFAULT 0,
  error_summary VARCHAR(1000) DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_run_id (run_id),
  KEY k_kind_start (kind, started_at),
  KEY k_status (kind, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""


def _env(name):
    return (os.environ.get(name) or "").strip()


def _env_int(name, default=0):
    v = _env(name)
    try:
        return int(v) if v else default
    except ValueError:
        return default


def _load_env_file(path):
    out = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip()
    return out


def _connect():
    import pymysql
    env = _load_env_file(ENV_PATH)
    return pymysql.connect(
        host=os.environ.get("DB_HOST") or env.get("DB_HOST") or "127.0.0.1",
        port=int(os.environ.get("DB_PORT") or env.get("DB_PORT") or 3308),
        user=os.environ.get("DB_USER") or env.get("DB_USER") or "n8nuser",
        password=os.environ.get("DB_PASS") or env.get("DB_PASS") or "",
        database=os.environ.get("DB_NAME") or env.get("DB_NAME") or "radio",
        charset="utf8mb4",
        connect_timeout=10,
    )


def _srt_in_window(conn, started_dt, finished_dt):
    """SRTs whose production time (updated_at) fell inside this run's window."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM radio_program_sessions "
            "WHERE is_subtitled=1 AND status='subtitled' "
            "AND updated_at >= %s AND updated_at < %s",
            (started_dt, finished_dt + timedelta(seconds=30)),
        )
        return int(cur.fetchone()[0] or 0)


def main():
    try:
        kind = _env("REC_KIND") or "pipeline"
        started = _env("REC_STARTED_AT")
        if kind not in ("pipeline", "site") or not started:
            print("record: FAILED: missing REC_KIND / REC_STARTED_AT")
            return
        status = _env("REC_STATUS") or "ok"
        error = _env("REC_ERROR")[:1000] or None

        started_dt = datetime.strptime(started[:19], "%Y-%m-%d %H:%M:%S")
        finished_dt = datetime.now()
        duration = max(int((finished_dt - started_dt).total_seconds()), 0)

        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(CREATE_TABLE)
            conn.commit()

            row = {
                "run_id": f"{kind}-{int(time.time())}-{uuid.uuid4().hex[:8]}",
                "kind": kind,
                "started_at": started_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "finished_at": finished_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "status": status,
                "error_summary": error,
                "duration_seconds": duration,
            }
            if kind == "pipeline":
                scan_new = _env_int("REC_SCAN_NEW")
                disc_new = _env_int("REC_DISC_NEW")
                dl_ok = _env_int("REC_DL_OK")
                dl_fail = _env_int("REC_DL_FAIL")
                new_sessions = scan_new + disc_new
                row.update(
                    discovered_programs=_env_int("REC_DISC_PROGRAMS"),
                    discovered_sessions=new_sessions,
                    new_sessions=new_sessions,
                    no_new_work=1 if (status == "ok" and new_sessions == 0) else 0,
                    queued_downloads=dl_ok + dl_fail,
                    download_success=dl_ok,
                    download_failure=dl_fail,
                    new_srt_count=_srt_in_window(conn, started_dt, finished_dt),
                )
            else:  # site
                row.update(
                    published_output_count=_env_int("REC_PUBLISHED"),
                    new_srt_count=_env_int("REC_SRT_NEW"),
                    new_txt_count=_env_int("REC_TXT_NEW"),
                    push_ok=1 if _env_int("REC_PUSH_OK") == 1 else 0,
                )

            cols = ",".join(row.keys())
            placeholders = ",".join(["%s"] * len(row))
            with conn.cursor() as cur:
                cur.execute(
                    f"INSERT IGNORE INTO pipeline_runs ({cols}) VALUES ({placeholders})",
                    tuple(row.values()),
                )
            conn.commit()
            print(
                f"record: {kind} run recorded "
                f"(status={status} new_sessions={row.get('new_sessions', 0)} "
                f"new_srt={row.get('new_srt_count', 0)} "
                f"published={row.get('published_output_count', 0)} "
                f"push_ok={row.get('push_ok', 0)} duration={duration}s)"
            )
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
    except Exception as e:  # noqa: BLE001 — must never break the pipeline
        print(f"record: FAILED: {str(e)[:300]}")


if __name__ == "__main__":
    main()
