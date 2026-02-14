-- Migration 014: Add pg_notify trigger for config changes
-- Description: Fires 'config_change' NOTIFY on command_configs, event_configs,
--              redemption_configs, and channels (default_cooldown) writes,
--              so bots can refresh in-memory caches instantly.

CREATE OR REPLACE FUNCTION fn_notify_config_change()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('config_change', json_build_object(
        'table', TG_TABLE_NAME,
        'channel_id', NEW.channel_id
    )::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION fn_notify_config_delete()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('config_change', json_build_object(
        'table', TG_TABLE_NAME,
        'channel_id', OLD.channel_id
    )::text);
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- command_configs
DROP TRIGGER IF EXISTS trg_command_configs_notify ON command_configs;
CREATE TRIGGER trg_command_configs_notify
    AFTER INSERT OR UPDATE ON command_configs
    FOR EACH ROW EXECUTE FUNCTION fn_notify_config_change();

DROP TRIGGER IF EXISTS trg_command_configs_notify_delete ON command_configs;
CREATE TRIGGER trg_command_configs_notify_delete
    AFTER DELETE ON command_configs
    FOR EACH ROW EXECUTE FUNCTION fn_notify_config_delete();

-- event_configs
DROP TRIGGER IF EXISTS trg_event_configs_notify ON event_configs;
CREATE TRIGGER trg_event_configs_notify
    AFTER INSERT OR UPDATE ON event_configs
    FOR EACH ROW EXECUTE FUNCTION fn_notify_config_change();

-- redemption_configs
DROP TRIGGER IF EXISTS trg_redemption_configs_notify ON redemption_configs;
CREATE TRIGGER trg_redemption_configs_notify
    AFTER INSERT OR UPDATE ON redemption_configs
    FOR EACH ROW EXECUTE FUNCTION fn_notify_config_change();

-- channels (default_cooldown changes)
CREATE OR REPLACE FUNCTION fn_notify_channel_defaults_change()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.default_cooldown IS DISTINCT FROM OLD.default_cooldown THEN
        PERFORM pg_notify('config_change', json_build_object(
            'table', 'channels',
            'channel_id', NEW.channel_id
        )::text);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_channels_notify_defaults ON channels;
CREATE TRIGGER trg_channels_notify_defaults
    AFTER UPDATE ON channels
    FOR EACH ROW EXECUTE FUNCTION fn_notify_channel_defaults_change();
