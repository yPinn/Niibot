-- 156: a token write must never fail because the channel row doesn't exist yet.
--
-- Migration 149's trigger on `tokens` enqueues a stream-schedule publish for
-- every broadcaster token write. stream_schedule_publish_queue.channel_id is a
-- FK to channels, and ChannelRepository.upsert_token writes the token *before*
-- ensuring the channels row in the same transaction — so a first sign-in (no
-- channels row yet) hit a FK violation and the whole OAuth callback failed.
-- upsert_token_only can write a broadcaster token without a channels row too.
--
-- A channel with no row has no stream schedule to publish, so skipping the
-- enqueue is exactly right; once the row exists, later token writes and every
-- schedule edit enqueue as before. Only the `tokens` branch changes.

CREATE OR REPLACE FUNCTION fn_enqueue_stream_schedule_publish()
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
        -- First sign-in: the channels row is created later in the same
        -- transaction. Nothing to publish for a channel that doesn't exist.
        IF NOT EXISTS (SELECT 1 FROM channels WHERE channel_id = NEW.user_id) THEN
            RETURN NEW;
        END IF;
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
