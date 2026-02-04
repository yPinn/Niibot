-- ============================================
-- Niibot — Initial Schema (consolidated)
-- Merges: twitch/database/schema.sql
--         twitch/database/analytics_schema.sql
--         discord/database/schema.sql
-- ============================================

-- ============================================
-- Shared function: auto-update updated_at
-- ============================================
CREATE OR REPLACE FUNCTION fn_update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- Twitch Core Tables
-- ============================================

-- OAuth tokens
CREATE TABLE IF NOT EXISTS tokens (
    user_id    TEXT PRIMARY KEY,
    token      TEXT NOT NULL,
    refresh    TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_tokens_updated_at ON tokens;
CREATE TRIGGER trg_tokens_updated_at
    BEFORE UPDATE ON tokens
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

-- Twitch channels (multi-channel support)
CREATE TABLE IF NOT EXISTS channels (
    channel_id   TEXT PRIMARY KEY,
    channel_name TEXT NOT NULL,
    enabled      BOOLEAN DEFAULT TRUE,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_channels_name    ON channels(channel_name);
CREATE INDEX IF NOT EXISTS idx_channels_enabled ON channels(enabled);

DROP TRIGGER IF EXISTS trg_channels_updated_at ON channels;
CREATE TRIGGER trg_channels_updated_at
    BEFORE UPDATE ON channels
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

-- Channel toggle NOTIFY (for Twitch bot real-time reloading)
CREATE OR REPLACE FUNCTION fn_notify_channel_toggle()
RETURNS TRIGGER AS $$
DECLARE
    payload TEXT;
BEGIN
    IF NEW.enabled IS DISTINCT FROM OLD.enabled THEN
        payload := json_build_object(
            'channel_id',   NEW.channel_id,
            'channel_name', NEW.channel_name,
            'enabled',      NEW.enabled
        )::text;
        PERFORM pg_notify('channel_toggle', payload);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_channels_notify_toggle ON channels;
CREATE TRIGGER trg_channels_notify_toggle
    AFTER UPDATE ON channels
    FOR EACH ROW EXECUTE FUNCTION fn_notify_channel_toggle();

-- Discord user cache (OAuth login info)
CREATE TABLE IF NOT EXISTS discord_users (
    user_id      TEXT PRIMARY KEY,
    username     TEXT NOT NULL,
    display_name TEXT,
    avatar       TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_discord_users_updated_at ON discord_users;
CREATE TRIGGER trg_discord_users_updated_at
    BEFORE UPDATE ON discord_users
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

-- ============================================
-- Twitch Analytics Tables
-- ============================================

-- Stream sessions
CREATE TABLE IF NOT EXISTS stream_sessions (
    id         SERIAL PRIMARY KEY,
    channel_id TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at   TIMESTAMPTZ,
    title      TEXT,
    game_name  TEXT,
    game_id    TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_channel_time ON stream_sessions(channel_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_active       ON stream_sessions(channel_id) WHERE ended_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_sessions_game         ON stream_sessions(game_id)    WHERE game_id IS NOT NULL;

-- Command usage statistics (aggregated per session per command)
CREATE TABLE IF NOT EXISTS command_stats (
    id           SERIAL PRIMARY KEY,
    session_id   INT  NOT NULL REFERENCES stream_sessions(id) ON DELETE CASCADE,
    channel_id   TEXT NOT NULL,
    command_name TEXT NOT NULL,
    usage_count  INT  DEFAULT 1,
    last_used_at TIMESTAMPTZ NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(session_id, command_name)
);

CREATE INDEX IF NOT EXISTS idx_cmd_session      ON command_stats(session_id, usage_count DESC);
CREATE INDEX IF NOT EXISTS idx_cmd_channel_time ON command_stats(channel_id, last_used_at DESC);

-- Stream events (follow / subscribe / raid)
CREATE TABLE IF NOT EXISTS stream_events (
    id           SERIAL PRIMARY KEY,
    session_id   INT  NOT NULL REFERENCES stream_sessions(id) ON DELETE CASCADE,
    channel_id   TEXT NOT NULL,
    event_type   TEXT NOT NULL CHECK (event_type IN ('follow', 'subscribe', 'raid')),
    user_id      TEXT,
    username     TEXT,
    display_name TEXT,
    metadata     JSONB,
    occurred_at  TIMESTAMPTZ NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_session ON stream_events(session_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_type    ON stream_events(channel_id, event_type, occurred_at DESC);

-- ============================================
-- Analytics Views
-- ============================================

CREATE OR REPLACE VIEW v_top_commands AS
SELECT session_id, channel_id, command_name, usage_count, last_used_at
FROM command_stats
ORDER BY session_id DESC, usage_count DESC;

CREATE OR REPLACE VIEW v_session_summary AS
SELECT
    s.id AS session_id,
    s.channel_id,
    s.started_at,
    s.ended_at,
    s.title,
    s.game_name,
    EXTRACT(EPOCH FROM (COALESCE(s.ended_at, NOW()) - s.started_at)) / 3600 AS duration_hours,
    COALESCE(SUM(c.usage_count), 0) AS total_commands,
    COALESCE(SUM(CASE WHEN e.event_type = 'follow'    THEN 1 END), 0) AS new_follows,
    COALESCE(SUM(CASE WHEN e.event_type = 'subscribe' THEN 1 END), 0) AS new_subs,
    COALESCE(SUM(CASE WHEN e.event_type = 'raid'      THEN 1 END), 0) AS raids_received
FROM stream_sessions s
LEFT JOIN command_stats c ON c.session_id = s.id
LEFT JOIN stream_events e ON e.session_id = s.id
GROUP BY s.id;

-- ============================================
-- Discord Birthday Tables
-- ============================================

-- User birthday data (global)
CREATE TABLE IF NOT EXISTS birthdays (
    user_id    BIGINT PRIMARY KEY,
    month      SMALLINT NOT NULL,
    day        SMALLINT NOT NULL,
    year       SMALLINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT ck_birthdays_valid_month CHECK (month BETWEEN 1 AND 12),
    CONSTRAINT ck_birthdays_valid_day   CHECK (day   BETWEEN 1 AND 31),
    CONSTRAINT ck_birthdays_valid_year  CHECK (year IS NULL OR year BETWEEN 1900 AND 2100)
);

CREATE INDEX IF NOT EXISTS idx_birthdays_month_day ON birthdays(month, day);

DROP TRIGGER IF EXISTS trg_birthdays_updated_at ON birthdays;
CREATE TRIGGER trg_birthdays_updated_at
    BEFORE UPDATE ON birthdays
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

-- Guild subscription relationships
CREATE TABLE IF NOT EXISTS birthday_subscriptions (
    guild_id   BIGINT NOT NULL,
    user_id    BIGINT NOT NULL REFERENCES birthdays(user_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (guild_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_guild ON birthday_subscriptions(guild_id);

-- Guild birthday settings
CREATE TABLE IF NOT EXISTS birthday_settings (
    guild_id         BIGINT PRIMARY KEY,
    channel_id       BIGINT NOT NULL,
    role_id          BIGINT NOT NULL,
    message_template TEXT DEFAULT '今天是 {users} 的生日，請各位送上祝福！',
    last_notified_date DATE,
    enabled          BOOLEAN DEFAULT TRUE,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_settings_enabled ON birthday_settings(enabled);

DROP TRIGGER IF EXISTS trg_birthday_settings_updated_at ON birthday_settings;
CREATE TRIGGER trg_birthday_settings_updated_at
    BEFORE UPDATE ON birthday_settings
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();
