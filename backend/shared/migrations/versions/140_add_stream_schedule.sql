-- Migration 140: Stream schedule (title/game auto-apply on a weekly or one-off cadence)
--
-- Two-tier model: stream_schedules is the "plan" level (recurring weekday or one-off
-- date, start time + duration) that Phase 2 will sync 1:1 to a Twitch Schedule segment.
-- stream_schedule_segments are sub-blocks inside a plan (offset from plan start) that
-- drive internal title/game auto-apply only — never synced to Twitch.
--
-- No pg_notify/cache wiring here (unlike command_configs/timers): schedule resolution
-- is only read on stream.online and a 60s live-only poll, not on every chat message,
-- so a per-request DB read is cheap enough that a TTL cache + invalidation trigger
-- would be pure overhead.

CREATE TABLE stream_schedule_settings (
    channel_id TEXT PRIMARY KEY REFERENCES channels(channel_id) ON DELETE CASCADE,
    timezone   TEXT NOT NULL DEFAULT 'Asia/Taipei'
               CHECK (char_length(timezone) BETWEEN 1 AND 64),
    enabled    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_stream_schedule_settings_updated_at
    BEFORE UPDATE ON stream_schedule_settings
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

CREATE TABLE stream_schedules (
    id               SERIAL PRIMARY KEY,
    channel_id       TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    kind             TEXT NOT NULL CHECK (kind IN ('recurring', 'one_off')),
    weekday          SMALLINT CHECK (weekday BETWEEN 0 AND 6), -- 0 = Monday, matches date.weekday()
    specific_date    DATE,
    start_time       TIME NOT NULL,
    duration_minutes INT NOT NULL CHECK (duration_minutes BETWEEN 1 AND 1440),
    title_template   TEXT NOT NULL DEFAULT '',
    enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_stream_schedules_kind_fields CHECK (
        (kind = 'recurring' AND weekday IS NOT NULL AND specific_date IS NULL)
        OR
        (kind = 'one_off' AND specific_date IS NOT NULL AND weekday IS NULL)
    )
);

-- Partial indexes match exactly the two lookup shapes the resolver issues:
-- "today's enabled one-offs" and "this weekday's enabled recurring plans".
CREATE INDEX idx_stream_schedules_recurring
    ON stream_schedules (channel_id, weekday)
    WHERE kind = 'recurring' AND enabled = TRUE;

CREATE INDEX idx_stream_schedules_one_off
    ON stream_schedules (channel_id, specific_date)
    WHERE kind = 'one_off' AND enabled = TRUE;

CREATE TRIGGER trg_stream_schedules_updated_at
    BEFORE UPDATE ON stream_schedules
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

-- channel_id is denormalized from stream_schedules (same convention as
-- command_stats.channel_id alongside session_id in 000_initial_schema.sql) so
-- the router can filter/verify ownership directly on this table instead of
-- joining through stream_schedules on every segment mutation.
CREATE TABLE stream_schedule_segments (
    id             SERIAL PRIMARY KEY,
    channel_id     TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    schedule_id    INT NOT NULL REFERENCES stream_schedules(id) ON DELETE CASCADE,
    offset_minutes INT NOT NULL DEFAULT 0 CHECK (offset_minutes >= 0),
    title_template TEXT NOT NULL,
    game_id        TEXT,
    game_name      TEXT,
    sort_order     INT NOT NULL DEFAULT 0,
    UNIQUE (schedule_id, offset_minutes)
);

CREATE INDEX idx_stream_schedule_segments_schedule
    ON stream_schedule_segments (schedule_id, offset_minutes);
