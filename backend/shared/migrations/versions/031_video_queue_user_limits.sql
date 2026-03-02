-- Migration 031: Add per-user controls to video_queue_settings
-- Adds independent chat/redemption toggles, per-user cooldown, and per-user queue limit.

ALTER TABLE video_queue_settings
    ADD COLUMN IF NOT EXISTS chat_enabled           BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS redemption_enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS user_cooldown_seconds  INT     NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS max_per_user           INT     NOT NULL DEFAULT 0;

COMMENT ON COLUMN video_queue_settings.chat_enabled IS
    'When false, !vq chat command is disabled (master enabled must also be true).';

COMMENT ON COLUMN video_queue_settings.redemption_enabled IS
    'When false, channel point redemptions are disabled (master enabled must also be true).';

COMMENT ON COLUMN video_queue_settings.user_cooldown_seconds IS
    'Minimum seconds a viewer must wait between chat requests. 0 = no restriction. Applies to chat only.';

COMMENT ON COLUMN video_queue_settings.max_per_user IS
    'Maximum number of active (queued/playing) entries per viewer. 0 = no restriction. Applies to chat and redemption.';
