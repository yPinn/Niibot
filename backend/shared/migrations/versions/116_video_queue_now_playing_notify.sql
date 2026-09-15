-- Notify the bot when a video queue entry starts playing, so it can post a
-- one-time "now playing" chat announcement (distinct from 106's
-- video_queue_updates, which wakes the overlay SSE stream and also fires on
-- incidental field patches to an already-playing row — using it here would
-- risk a duplicate chat announcement).
--
-- Scoped to the status transition INTO 'playing' only: rows are always
-- INSERTed as 'queued' (021_add_video_queue's column default), so this is
-- always an UPDATE, never an INSERT.

CREATE OR REPLACE FUNCTION notify_video_queue_now_playing()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    PERFORM pg_notify('video_queue_now_playing',
        json_build_object('channel_id', NEW.channel_id)::TEXT);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_notify_video_queue_now_playing ON video_queue;
CREATE TRIGGER trg_notify_video_queue_now_playing
AFTER UPDATE OF status ON video_queue
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status AND NEW.status = 'playing')
EXECUTE FUNCTION notify_video_queue_now_playing();
