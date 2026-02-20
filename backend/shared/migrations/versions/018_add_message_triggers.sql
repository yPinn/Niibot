-- Migration 018: Add message_triggers table
-- Triggers respond to non-command chat messages matching a pattern

CREATE TABLE message_triggers (
    id             SERIAL PRIMARY KEY,
    channel_id     TEXT NOT NULL,
    trigger_name   TEXT NOT NULL,
    match_type     TEXT NOT NULL DEFAULT 'contains'
        CHECK (match_type IN ('contains', 'startswith', 'exact', 'regex')),
    pattern        TEXT NOT NULL,
    case_sensitive BOOLEAN NOT NULL DEFAULT FALSE,
    response       TEXT NOT NULL,
    min_role       TEXT NOT NULL DEFAULT 'everyone'
        CHECK (min_role IN ('everyone', 'subscriber', 'vip', 'moderator', 'broadcaster')),
    cooldown       INT,
    priority       INT NOT NULL DEFAULT 0,
    enabled        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(channel_id, trigger_name)
);

DROP TRIGGER IF EXISTS trg_message_triggers_updated_at ON message_triggers;
CREATE TRIGGER trg_message_triggers_updated_at
    BEFORE UPDATE ON message_triggers
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

-- Reuse existing notify functions (fn_notify_config_change uses NEW, fn_notify_config_delete uses OLD)
DROP TRIGGER IF EXISTS trg_message_triggers_notify_change ON message_triggers;
CREATE TRIGGER trg_message_triggers_notify_change
    AFTER INSERT OR UPDATE ON message_triggers
    FOR EACH ROW EXECUTE FUNCTION fn_notify_config_change();

DROP TRIGGER IF EXISTS trg_message_triggers_notify_delete ON message_triggers;
CREATE TRIGGER trg_message_triggers_notify_delete
    AFTER DELETE ON message_triggers
    FOR EACH ROW EXECUTE FUNCTION fn_notify_config_delete();

ALTER TABLE message_triggers ENABLE ROW LEVEL SECURITY;
GRANT ALL ON message_triggers TO anon, authenticated, service_role;
GRANT USAGE, SELECT ON SEQUENCE message_triggers_id_seq TO anon, authenticated, service_role;
