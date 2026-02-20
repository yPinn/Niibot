-- Migration 017: Add timers table
-- Timers send scheduled messages during live streams (dual-trigger: time + min chat lines)

CREATE TABLE timers (
    id               SERIAL PRIMARY KEY,
    channel_id       TEXT NOT NULL,
    timer_name       TEXT NOT NULL,
    interval_seconds INT NOT NULL CHECK (interval_seconds >= 60),
    min_lines        INT NOT NULL DEFAULT 5,
    message_template TEXT NOT NULL,
    enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(channel_id, timer_name)
);

DROP TRIGGER IF EXISTS trg_timers_updated_at ON timers;
CREATE TRIGGER trg_timers_updated_at
    BEFORE UPDATE ON timers
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

-- Reuse existing notify functions (fn_notify_config_change uses NEW, fn_notify_config_delete uses OLD)
DROP TRIGGER IF EXISTS trg_timers_notify_change ON timers;
CREATE TRIGGER trg_timers_notify_change
    AFTER INSERT OR UPDATE ON timers
    FOR EACH ROW EXECUTE FUNCTION fn_notify_config_change();

DROP TRIGGER IF EXISTS trg_timers_notify_delete ON timers;
CREATE TRIGGER trg_timers_notify_delete
    AFTER DELETE ON timers
    FOR EACH ROW EXECUTE FUNCTION fn_notify_config_delete();

ALTER TABLE timers ENABLE ROW LEVEL SECURITY;
GRANT ALL ON timers TO anon, authenticated, service_role;
GRANT USAGE, SELECT ON SEQUENCE timers_id_seq TO anon, authenticated, service_role;
