-- Migration 035: Change max_duration_redemption default from 1200s (20min) to 600s (10min).
-- 10 minutes is a more sensible default for channel-point redemptions.
ALTER TABLE video_queue_settings
    ALTER COLUMN max_duration_redemption SET DEFAULT 600;
