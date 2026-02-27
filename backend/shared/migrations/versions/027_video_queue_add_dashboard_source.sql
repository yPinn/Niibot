-- Migration 027: Allow 'dashboard' as a valid source in video_queue
--
-- The original inline CHECK on the `source` column was auto-named
-- `video_queue_source_check` by PostgreSQL (standard naming convention
-- for unnamed inline constraints: {table}_{column}_check).
-- Drop it with IF EXISTS (safe regardless of exact name) and re-add
-- with the extended value list.

ALTER TABLE video_queue DROP CONSTRAINT IF EXISTS video_queue_source_check;

ALTER TABLE video_queue
    ADD CONSTRAINT video_queue_source_check
    CHECK (source IN ('chat', 'redemption', 'dashboard'));
