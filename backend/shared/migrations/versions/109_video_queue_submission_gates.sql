-- 109: submission gates for video_queue_settings.
--
-- max_duration_seconds  — global length cap applied to chat + dashboard adds
--   (redemption keeps its own max_duration_redemption); 0 = no limit.
-- replay_cooldown_hours — reject a video played within the last N hours,
--   checked against the done/skipped history rows; 0 = no limit.

ALTER TABLE video_queue_settings
    ADD COLUMN IF NOT EXISTS max_duration_seconds INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS replay_cooldown_hours INT NOT NULL DEFAULT 0;
