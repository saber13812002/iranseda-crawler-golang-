
-- Add legacy tracking columns to radio_programs
ALTER TABLE `radio_programs`
    ADD COLUMN IF NOT EXISTS `is_legacy` TINYINT(1) NOT NULL DEFAULT 0 AFTER `radio_id`,
    ADD COLUMN IF NOT EXISTS `legacy_expires_at` TIMESTAMP NULL DEFAULT NULL AFTER `is_legacy`;
