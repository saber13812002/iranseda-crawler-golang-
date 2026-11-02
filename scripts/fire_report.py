#!/usr/bin/env python3
"""fire_report.py — standalone, best-effort reporter event recorder.

Called from the cron scripts (run_pipeline.sh, refresh_site.sh) to drop a
row into publication_task (status='queued') that the dashboard reporter
worker (dashboard/reporter.py) later publishes to the configured
Telegram/Bale client (dashboard/messenger_publisher.py) when
IRANSEDA_REPORTER_ENABLED=1.

Everything arrives via REP_* environment variables:
  REP_EVENT_TYPE  required (download_batch | transcribe_batch | git_release | ...)
  REP_TITLE       required (truncated to 200 chars)
  REP_BODY        optional
  REP_COMMIT      optional git commit sha (truncated to 64 chars)
  REP_URL         optional artifact url (truncated to 512 chars)
  REP_KEY         optional explicit idempotency key (default: sha1 of
                  event_type+title+url+commit — the SAME formula as
                  dashboard/reporter.py, so a re-fired identical event is a
                  no-op and never re-submits an in-flight/terminal task)

Best-effort by contract (like record_run.py): it NEVER raises into the
caller and ALWAYS exits 0. On any error it prints "report: FAILED: ..." so
the pipeline log shows what happened without the run being blamed.

Creates the publication_task table if the dashboard has not created it yet
(the DDL mirrors dashboard/llm_jobs.py exactly), so this also works on a
fresh DB.
"""
import hashlib
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT, ".env")

# Mirror of dashboard/llm_jobs.py publication_task DDL (keep in sync).
CREATE_TABLE = """CREATE TABLE IF NOT EXISTS publication_task (
    id INT AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(64) NOT NULL,
    title VARCHAR(200),
    body TEXT,
    artifact_url VARCHAR(512) NULL,
    git_commit VARCHAR(64) NULL,
    external_task_id VARCHAR(128) NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'queued',
    channels VARCHAR(255) NULL,
    submitted_at DATETIME NULL,
    check_after DATETIME NULL,
    published_at DATETIME NULL,
    post_urls TEXT NULL,
    views TEXT NULL,
    last_checked_at DATETIME NULL,
    error VARCHAR(500) NULL,
    idempotency_key VARCHAR(191) NOT NULL UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP,
    attempts TINYINT NOT NULL DEFAULT 0,
    KEY k_pub_status (status, check_after)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""


def _env(name):
    return (os.environ.get(name) or "").strip()


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
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
    )


def default_key(event_type, title, url, commit):
    # Same formula as reporter.default_idempotency_key — one row per logical
    # event, across both entry points.
    return hashlib.sha1(
        ("%s%s%s%s" % (event_type, title or "", url or "", commit or ""))
        .encode("utf-8")).hexdigest()


def main():
    try:
        event_type = _env("REP_EVENT_TYPE")
        title = _env("REP_TITLE")
        if not event_type or not title:
            print("report: FAILED: REP_EVENT_TYPE / REP_TITLE missing")
            return
        body = _env("REP_BODY") or None
        commit = _env("REP_COMMIT") or None
        url = _env("REP_URL") or None
        key = _env("REP_KEY") or default_key(event_type, title, url, commit)

        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(CREATE_TABLE)
            conn.commit()
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO publication_task "
                    "(event_type, title, body, artifact_url, git_commit, "
                    " channels, idempotency_key, status, attempts) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,'queued',0) "
                    "ON DUPLICATE KEY UPDATE title=VALUES(title), "
                    "body=VALUES(body)",
                    (event_type, title[:200], body,
                     url[:512] if url else None,
                     commit[:64] if commit else None, None, key))
                conn.commit()
                cur.execute(
                    "SELECT id, status FROM publication_task "
                    "WHERE idempotency_key=%s", (key,))
                row = cur.fetchone()
            print("report: %s recorded (task=%s status=%s key=%s...)"
                  % (event_type, row["id"], row["status"], key[:12]))
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
    except Exception as e:  # noqa: BLE001 — must never break the pipeline
        print("report: FAILED: %s" % str(e)[:300])


if __name__ == "__main__":
    main()
