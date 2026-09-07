-- 108: Twitch VOD support for video_queue.
--
-- A VOD (twitch.tv/videos/{id}) is played as a bounded window: seek to
-- start_seconds (the URL's `?t=` offset) and play for duration_seconds (the
-- registry caps this at TWITCH_VOD_WINDOW_SECONDS). start_seconds is set once
-- at INSERT and never updated, so it stays out of the migration-106 NOTIFY
-- trigger's column list (same as is_vertical / video_type).

ALTER TABLE video_queue
    ADD COLUMN IF NOT EXISTS start_seconds INT NOT NULL DEFAULT 0;

ALTER TABLE video_queue DROP CONSTRAINT IF EXISTS video_queue_video_type_check;
ALTER TABLE video_queue ADD CONSTRAINT video_queue_video_type_check
    CHECK (video_type IN ('youtube', 'twitch_clip', 'twitch_vod', 'bilibili'));
