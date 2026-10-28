-- 2026-10-28: per-run pipeline records for 30-minute cron observability.
--
-- One row per cron run, written by scripts/record_run.py at the end of
-- every scripts/run_pipeline.sh (kind='pipeline': scan + discover + download)
-- and scripts/refresh_site.sh (kind='site': generate + git push).
-- All timestamps are UTC (same convention as radio_program_sessions).
--
-- The table is ALSO created idempotently by record_run.py itself
-- (CREATE TABLE IF NOT EXISTS), so this file doubles as documentation
-- and a manual migration. Safe to run: uses IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS pipeline_runs (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='One row per 30-min cron run (pipeline/site)';
