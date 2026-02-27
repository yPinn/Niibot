-- Migration 026: Add min_view_count to video_queue_settings
-- When set > 0, videos with fewer views than this threshold are rejected.

ALTER TABLE video_queue_settings
    ADD COLUMN IF NOT EXISTS min_view_count INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN video_queue_settings.min_view_count IS
    'Minimum YouTube view count required to add a video. 0 = no restriction.';
