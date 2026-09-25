-- Migration: session pipeline status tracking
-- Makes the whole download -> transcribe -> srt pipeline visible per session in the DB.
-- Apply with: mysql -h127.0.0.1 -P3308 -uroot -prootpass radio < 2026-09-25_session_pipeline_status.sql

ALTER TABLE radio_program_sessions
  ADD COLUMN status VARCHAR(24) NOT NULL DEFAULT 'unknown' AFTER is_downloaded,
  ADD COLUMN is_subtitled TINYINT NOT NULL DEFAULT 0 AFTER status,
  ADD COLUMN srt_filename VARCHAR(255) DEFAULT NULL AFTER filename,
  ADD COLUMN attempts TINYINT NOT NULL DEFAULT 0 AFTER is_subtitled,
  ADD COLUMN last_error VARCHAR(500) DEFAULT NULL,
  ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  ADD INDEX idx_session_status (status);

-- Initial backfill (refined per-file by scripts/backfill_session_status.py afterwards)
UPDATE radio_program_sessions
SET status = CASE WHEN is_downloaded = 1 THEN 'downloaded' ELSE 'pending_download' END;
