-- Migration: program discovery + admin settings (STEP 13)
-- Additive only, idempotent (CREATE TABLE IF NOT EXISTS).
--
-- Two tables power the admin panel's "discover programs from radio.iranseda.ir
-- and add with one click" flow:
--
--   program_discovery  — one row per PROGRAM found on the site, keyed by the
--                        stable 8-digit program id `m` (NOT the per-broadcast
--                        `e` event id). The dashboard's discovery UI upserts
--                        these as the user browses channels.
--   program_settings   — one row per activated program (radio_programs.id):
--                        the processing start point chosen at activation, the
--                        discovery run state (where the periodic scan stopped),
--                        and the one-time start-point seeding status.
--
-- Activation itself still lives in radio_programs (is_legacy=0) — the single
-- source of truth scan.go reads. Nothing here duplicates the download/ASR
-- pipeline; program_settings only remembers HOW the archive was walked.
--
-- Apply with (on server 53):
--   docker exec -i iranseda-mysql mysql -un8nuser -p"StrongPassword123!" \
--     --default-character-set=utf8mb4 radio < 2026-10-21_program_discovery.sql

CREATE TABLE IF NOT EXISTS `program_discovery` (
  `id`              INT NOT NULL AUTO_INCREMENT,
  `m`               VARCHAR(8) NOT NULL,          -- stable program id (site `m=` param)
  `ch`              INT NOT NULL,                 -- channel id (site `ch=` param)
  `channel_name`    VARCHAR(120) DEFAULT NULL,    -- e.g. رادیو معارف
  `name`            VARCHAR(255) NOT NULL,        -- as listed on programlist (incl. schedule suffix)
  `url`             VARCHAR(255) NOT NULL,        -- https://radio.iranseda.ir/Program/?VALID=TRUE&ch=..&m=..
  `first_seen_at`   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `last_seen_at`    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_m` (`m`),
  KEY `k_ch` (`ch`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `program_settings` (
  `id`               INT NOT NULL AUTO_INCREMENT,
  `program_id`       INT NOT NULL,                -- radio_programs.id
  `start_mode`       VARCHAR(16) NOT NULL DEFAULT 'new_only',  -- from_start | from_date | new_only
  `start_date`       DATE DEFAULT NULL,           -- used when start_mode = from_date
  `seeded`           TINYINT NOT NULL DEFAULT 0,  -- 1 = start-point seeding done (or nothing to seed)
  `seeded_at`        DATETIME DEFAULT NULL,
  `last_discovery_at` DATETIME DEFAULT NULL,      -- last periodic archive walk
  `discovery_note`   VARCHAR(255) DEFAULT NULL,   -- last walk result / error
  `created_at`       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_program` (`program_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
