-- 005: Add event_configs table for configurable event response templates

-- 建立表
CREATE TABLE IF NOT EXISTS event_configs (
    id               SERIAL PRIMARY KEY,
    channel_id       TEXT NOT NULL,
    event_type       TEXT NOT NULL CHECK (event_type IN ('follow', 'subscribe', 'raid')),
    message_template TEXT NOT NULL,
    enabled          BOOLEAN DEFAULT TRUE,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(channel_id, event_type)
);

CREATE INDEX IF NOT EXISTS idx_event_configs_channel ON event_configs(channel_id);

-- updated_at 自動更新 trigger（複用現有 fn_update_updated_at）
DROP TRIGGER IF EXISTS trg_event_configs_updated_at ON event_configs;
CREATE TRIGGER trg_event_configs_updated_at
    BEFORE UPDATE ON event_configs
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

