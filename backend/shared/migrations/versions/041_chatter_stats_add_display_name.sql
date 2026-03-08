-- ============================================
-- 041: Add display_name to chatter_stats
-- Aligns with stream_events which already stores display_name.
-- NULL for existing rows; new rows populated from Twitch chat payload.
-- ============================================

ALTER TABLE chatter_stats ADD COLUMN IF NOT EXISTS display_name TEXT;
