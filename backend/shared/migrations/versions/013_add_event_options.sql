-- 013: Add options JSONB column to event_configs for per-event settings
-- Used by raid auto_shoutout and future extensible per-event options.

ALTER TABLE event_configs ADD COLUMN IF NOT EXISTS options JSONB DEFAULT '{}';
