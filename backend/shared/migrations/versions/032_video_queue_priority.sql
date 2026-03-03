-- Migration 032: Add priority column to video_queue for tier-based ordering
--
-- Priority tiers (higher value = plays first within the same channel):
--   chat       → 0   (default, chat !vq command)
--   redemption → 10  (channel point redemption)
--   donation   → 20  (reserved for future payment platform integration)
--   dashboard  → 30  (broadcaster direct add)
--   99 is reserved internally for set_as_next pinning (not stored as a source)
--
-- Ordering: ORDER BY priority DESC, created_at ASC
--   Higher priority sources always play before lower priority ones.
--   Within the same tier, entries are served FIFO.

ALTER TABLE video_queue ADD COLUMN IF NOT EXISTS priority INT NOT NULL DEFAULT 0;

-- Backfill existing rows based on their source
UPDATE video_queue
SET priority = CASE source
    WHEN 'chat'        THEN 0
    WHEN 'redemption'  THEN 10
    WHEN 'donation'    THEN 20
    WHEN 'dashboard'   THEN 30
    ELSE 0
END;

-- Reserve 'donation' source for future payment platform integration
ALTER TABLE video_queue DROP CONSTRAINT IF EXISTS video_queue_source_check;
ALTER TABLE video_queue
    ADD CONSTRAINT video_queue_source_check
    CHECK (source IN ('chat', 'redemption', 'dashboard', 'donation'));

-- Replace the existing channel/status index with a priority-aware composite index.
-- The new index supports the ORDER BY priority DESC, created_at ASC query pattern.
DROP INDEX IF EXISTS idx_video_queue_channel_status;
CREATE INDEX idx_video_queue_channel_status
    ON video_queue (channel_id, status, priority DESC, created_at ASC);
