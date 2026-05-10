-- 058: Add display_name to channels for storing Twitch display name separately from login name

ALTER TABLE channels ADD COLUMN IF NOT EXISTS display_name TEXT;
