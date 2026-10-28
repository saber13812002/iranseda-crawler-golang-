-- 2026-10-28: enforce episode-level dedup in radio_program_sessions.
--
-- Background (STEP 2, Task A):
--   radio_program_sessions had NO unique key on (program_id, link), so every
--   "INSERT IGNORE" in the pipeline was effectively a plain INSERT and all
--   dedup was exact-string, in-memory only. The same episode reached by a
--   differently-formatted URL (absolute vs relative, VALID flag, param
--   order, trailing slash) could create a duplicate queue row.
--
-- Safety check that must PASS before applying (it did, 2026-10-28):
--   SELECT COUNT(*) FROM (
--     SELECT program_id, link FROM radio_program_sessions
--     GROUP BY program_id, link HAVING COUNT(*) > 1) t;
--   -> expected 0 (0 before applying; if ever non-zero, de-duplicate first,
--      keeping the MIN(id) per pair, instead of running this as-is).
--
-- Note: the key is on the RAW link (not the canonical form) on purpose —
-- it is the last-resort safety net; the canonical-key matching in
-- discover_new.py / logic.py / scan.go is the primary dedup and also catches
-- format-variant duplicates. No historical rows are modified.

ALTER TABLE radio_program_sessions
  ADD CONSTRAINT uq_session_program_link UNIQUE (program_id, link);
