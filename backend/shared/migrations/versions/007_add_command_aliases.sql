-- 007: Add aliases column to command_configs

ALTER TABLE command_configs ADD COLUMN IF NOT EXISTS aliases TEXT;
-- Comma-separated alias names, e.g. "hello,嗨,hey"
