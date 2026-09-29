-- Migration 149: reliable, one-way Niibot -> Twitch Schedule publication.

CREATE TABLE stream_schedule_twitch_states (
    id                  BIGSERIAL PRIMARY KEY,
    channel_id          TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    schedule_id         INT,
    twitch_segment_id   TEXT,
    schedule_kind       TEXT NOT NULL CHECK (schedule_kind IN ('recurring', 'one_off')),
    identity_key        TEXT,
    payload_fingerprint TEXT,
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'synced', 'blocked', 'error')),
    error_code          TEXT,
    attempt_count       INT NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_attempted_at   TIMESTAMPTZ,
    synced_at           TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (channel_id, schedule_id),
    UNIQUE (channel_id, twitch_segment_id)
);

CREATE INDEX idx_stream_schedule_twitch_states_orphan
    ON stream_schedule_twitch_states (channel_id)
    WHERE schedule_id IS NULL;

CREATE TABLE stream_schedule_twitch_occurrences (
    id                    BIGSERIAL PRIMARY KEY,
    channel_id            TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    recurring_schedule_id INT NOT NULL,
    occurrence_date       DATE NOT NULL,
    twitch_segment_id     TEXT,
    desired_state         TEXT NOT NULL CHECK (desired_state IN ('active', 'cancelled')),
    status                TEXT NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'deferred', 'synced', 'blocked', 'error')),
    error_code            TEXT,
    last_attempted_at     TIMESTAMPTZ,
    synced_at             TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (channel_id, recurring_schedule_id, occurrence_date)
);

CREATE TABLE stream_schedule_publish_queue (
    channel_id      TEXT PRIMARY KEY REFERENCES channels(channel_id) ON DELETE CASCADE,
    generation      BIGINT NOT NULL DEFAULT 1,
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    available_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    attempt_count   INT NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    locked_at       TIMESTAMPTZ,
    last_error_code TEXT
);

CREATE FUNCTION fn_enqueue_stream_schedule_publish()
RETURNS TRIGGER AS $$
DECLARE
    target_channel_id TEXT;
BEGIN
    IF TG_TABLE_NAME = 'stream_schedule_segments' THEN
        IF TG_OP = 'INSERT' AND NEW.offset_minutes <> 0 THEN RETURN NEW; END IF;
        IF TG_OP = 'DELETE' AND OLD.offset_minutes <> 0 THEN RETURN OLD; END IF;
        IF TG_OP = 'UPDATE'
           AND NEW.offset_minutes <> 0
           AND OLD.offset_minutes <> 0 THEN
            RETURN NEW;
        END IF;
    END IF;

    IF TG_TABLE_NAME = 'tokens' THEN
        IF NEW.token_type <> 'broadcaster' THEN RETURN NEW; END IF;
        target_channel_id := NEW.user_id;
    ELSIF TG_OP = 'DELETE' THEN
        target_channel_id := OLD.channel_id;
    ELSE
        target_channel_id := NEW.channel_id;
    END IF;

    INSERT INTO stream_schedule_publish_queue (channel_id)
    VALUES (target_channel_id)
    ON CONFLICT (channel_id) DO UPDATE SET
        generation = stream_schedule_publish_queue.generation + 1,
        requested_at = NOW(),
        available_at = NOW(),
        attempt_count = 0,
        last_error_code = NULL;

    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_stream_schedule_publish_settings
AFTER UPDATE OF timezone, enabled ON stream_schedule_settings
FOR EACH ROW EXECUTE FUNCTION fn_enqueue_stream_schedule_publish();

CREATE TRIGGER trg_stream_schedule_publish_schedules
AFTER INSERT OR UPDATE OR DELETE ON stream_schedules
FOR EACH ROW EXECUTE FUNCTION fn_enqueue_stream_schedule_publish();

CREATE TRIGGER trg_stream_schedule_publish_segments
AFTER INSERT OR UPDATE OR DELETE ON stream_schedule_segments
FOR EACH ROW EXECUTE FUNCTION fn_enqueue_stream_schedule_publish();

CREATE TRIGGER trg_stream_schedule_publish_occurrences
AFTER INSERT OR UPDATE OR DELETE ON stream_schedule_occurrence_exceptions
FOR EACH ROW EXECUTE FUNCTION fn_enqueue_stream_schedule_publish();

CREATE TRIGGER trg_stream_schedule_publish_token_insert
AFTER INSERT ON tokens
FOR EACH ROW EXECUTE FUNCTION fn_enqueue_stream_schedule_publish();

CREATE TRIGGER trg_stream_schedule_publish_token_update
AFTER UPDATE OF scopes, credential_revision, requires_reauth ON tokens
FOR EACH ROW EXECUTE FUNCTION fn_enqueue_stream_schedule_publish();

INSERT INTO stream_schedule_publish_queue (channel_id)
SELECT DISTINCT channel_id FROM stream_schedules
ON CONFLICT (channel_id) DO NOTHING;
