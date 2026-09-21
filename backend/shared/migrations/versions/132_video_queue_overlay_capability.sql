-- A dedicated, rotatable capability authorises state changes from the OBS
-- Video Queue overlay without coupling it to the Live Display overlay key.
ALTER TABLE video_queue_settings
    ADD COLUMN IF NOT EXISTS overlay_key UUID NOT NULL DEFAULT gen_random_uuid();

CREATE UNIQUE INDEX IF NOT EXISTS uq_video_queue_settings_overlay_key
    ON video_queue_settings (overlay_key);
