-- Add enabled_packs to ai_settings for per-channel knowledge pack selection.
ALTER TABLE ai_settings
    ADD COLUMN IF NOT EXISTS enabled_packs TEXT[] NOT NULL DEFAULT '{}';
