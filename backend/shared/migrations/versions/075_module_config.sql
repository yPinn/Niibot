-- Remove per-channel enabled_packs from ai_settings; replace with global module_config table.
ALTER TABLE ai_settings DROP COLUMN IF EXISTS enabled_packs;

CREATE TABLE IF NOT EXISTS module_config (
    key        TEXT PRIMARY KEY,
    value      JSONB NOT NULL DEFAULT 'null'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO module_config (key, value)
VALUES ('enabled_packs', '[]'::jsonb)
ON CONFLICT (key) DO NOTHING;
