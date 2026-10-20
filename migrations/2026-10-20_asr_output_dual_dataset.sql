-- Migration: dual-ASR output registry (STEP 12 — Roshan ASR Pilot)
-- Additive only. Records an independent, versioned ASR output per session +
-- provider + model/pipeline version + audio hash, so Roshan output never
-- overwrites Whisper and historical versions survive re-runs.
--
-- The existing `llm_output` table is LLM-pipeline specific (prompt_id,
-- input/output_tokens, unique on job_type+model) and is NOT fit for a
-- provider-versioned ASR artifact, so a small dedicated table is created.
--
-- Apply with (on server 53):
--   docker exec -i iranseda-mysql mysql -un8nuser -p"StrongPassword123!" --default-character-set=utf8mb4 radio < 2026-10-20_asr_output_dual_dataset.sql
-- Idempotent: CREATE TABLE IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS `asr_output` (
  `id`              BIGINT NOT NULL AUTO_INCREMENT,
  `session_id`      INT NOT NULL,
  `program_id`      INT DEFAULT NULL,
  `provider`        VARCHAR(32) NOT NULL,           -- 'whisper' | 'roshan' | ...
  `model_name`      VARCHAR(120) NOT NULL,           -- e.g. asr-ismc-fa / whisper-persian-v4
  `model_version`   VARCHAR(64) DEFAULT NULL,        -- upstream model version if exposed
  `pipeline_version` VARCHAR(32) DEFAULT NULL,       -- our processing-pipeline version (e.g. v1)
  `audio_sha256`    CHAR(64) DEFAULT NULL,           -- of the exact audio that produced this
  `processing_status` VARCHAR(24) NOT NULL DEFAULT 'pending',  -- pending|running|done|text_only|failed
  `srt_path`        VARCHAR(300) DEFAULT NULL,       -- NULL when TEXT_ONLY
  `fulltext_path`   VARCHAR(300) DEFAULT NULL,
  `raw_response_path` VARCHAR(300) DEFAULT NULL,
  `duration_ms`     INT DEFAULT NULL,                -- audio length this output covers
  `segment_count`   INT DEFAULT NULL,
  `word_count`      INT DEFAULT NULL,
  `latency_ms`      INT DEFAULT NULL,                -- ASR wall time for this output
  `rtf`             DECIMAL(6,4) DEFAULT NULL,       -- realtime factor = latency/duration
  `created_at`      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `error_code`      VARCHAR(64) DEFAULT NULL,
  `error_message`   VARCHAR(500) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_asr` (`session_id`,`provider`,`pipeline_version`,`audio_sha256`),
  KEY `k_asr_session` (`session_id`),
  KEY `k_asr_provider` (`provider`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
