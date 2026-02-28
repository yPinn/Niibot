-- Migration 030: add is_vertical to video_queue
-- Tracks whether the video is vertical (e.g. YouTube Shorts) for overlay layout switching.

ALTER TABLE video_queue
    ADD COLUMN IF NOT EXISTS is_vertical BOOLEAN NOT NULL DEFAULT FALSE;
