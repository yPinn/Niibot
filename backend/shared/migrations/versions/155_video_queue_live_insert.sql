-- 155: Video Queue live insert (直播插播).
--
-- A broadcaster-only, open-ended playback of someone's ongoing live stream
-- (Twitch channel or YouTube live) — background music, a watch-along. It is
-- deliberately NOT a video_queue row: it has no length, no review, no place in
-- line, and never ends on its own. While one is active the queue is paused
-- (the app's promote queries skip channels with an active insert); the entry
-- that was playing goes back to the front of the queue.
--
-- At most one insert per channel (UNIQUE channel_id). `id` is a fresh identity
-- per start so the overlay can end exactly the insert it was playing — a stale
-- end report never stops a newer insert. "Active" is enforced by the app as
-- started_at within the last 12 hours, so a forgotten insert cannot resume on
-- the next broadcast (Niibot does not detect whether the streamer is live).
--
-- volume_percent / audio_only are copied from the settings defaults at start
-- and live on the row: the overlay reads playback config from the NOTIFY-woken
-- stream, and video_queue_settings has no trigger (see 106).

ALTER TABLE video_queue_settings
    ADD COLUMN IF NOT EXISTS insert_volume_percent SMALLINT NOT NULL DEFAULT 30,
    ADD COLUMN IF NOT EXISTS insert_audio_only BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE video_queue_settings
    DROP CONSTRAINT IF EXISTS chk_video_queue_insert_volume_percent;

ALTER TABLE video_queue_settings
    ADD CONSTRAINT chk_video_queue_insert_volume_percent
    CHECK (insert_volume_percent BETWEEN 0 AND 100);

CREATE TABLE IF NOT EXISTS video_queue_inserts (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel_id     TEXT NOT NULL UNIQUE REFERENCES channels(channel_id) ON DELETE CASCADE,
    source_type    TEXT NOT NULL CHECK (source_type IN ('twitch_live', 'youtube_live')),
    source_id      TEXT NOT NULL,
    title          TEXT,
    creator_id     TEXT,
    creator_name   TEXT,
    thumbnail_url  TEXT,
    volume_percent SMALLINT NOT NULL CHECK (volume_percent BETWEEN 0 AND 100),
    audio_only     BOOLEAN NOT NULL DEFAULT FALSE,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Wake the same Video Queue stream consumers as 106. DELETE has no NEW row,
-- so the function reads whichever row exists.
CREATE OR REPLACE FUNCTION notify_video_queue_insert_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    PERFORM pg_notify('video_queue_updates',
        json_build_object('channel_id', COALESCE(NEW.channel_id, OLD.channel_id))::TEXT);
    RETURN COALESCE(NEW, OLD);
END;
$$;

DROP TRIGGER IF EXISTS trg_notify_video_queue_insert_change ON video_queue_inserts;
CREATE TRIGGER trg_notify_video_queue_insert_change
AFTER INSERT OR UPDATE OR DELETE ON video_queue_inserts
FOR EACH ROW EXECUTE FUNCTION notify_video_queue_insert_change();
