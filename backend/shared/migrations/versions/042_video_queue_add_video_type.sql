-- Migration 042: Add video_type column to video_queue
-- Supports 'youtube' (existing) and 'twitch_clip' (new) as video sources.
-- All existing rows default to 'youtube'.

ALTER TABLE video_queue
    ADD COLUMN video_type TEXT NOT NULL DEFAULT 'youtube'
    CHECK (video_type IN ('youtube', 'twitch_clip'));
