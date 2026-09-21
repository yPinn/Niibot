-- Explicit normalized overlay volume for providers with a controllable player.
ALTER TABLE video_queue_settings
    ADD COLUMN IF NOT EXISTS volume_percent SMALLINT NOT NULL DEFAULT 100;

ALTER TABLE video_queue_settings
    DROP CONSTRAINT IF EXISTS chk_video_queue_volume_percent;

ALTER TABLE video_queue_settings
    ADD CONSTRAINT chk_video_queue_volume_percent
    CHECK (volume_percent BETWEEN 0 AND 100);
