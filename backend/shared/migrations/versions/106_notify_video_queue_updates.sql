-- Wake Video Queue overlay stream consumers after durable state commits.
-- The table remains the data source; NOTIFY contains no capability or user content.
--
-- video_queue_settings has no trigger: the overlay renderer never reads settings
-- (only current/queue/queue_size), and the 15s in-process settings cache
-- (VideoQueueSettingsRepository._settings_cache) would make a streamed value
-- dishonestly stale even if it did.
--
-- Postgres forbids a WHEN clause that references OLD on a trigger that also
-- fires for INSERT (OLD is undefined there), so INSERT and UPDATE are split
-- into two triggers sharing one function, following 104's dispatch pattern.

CREATE OR REPLACE FUNCTION notify_video_queue_update()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    PERFORM pg_notify('video_queue_updates',
        json_build_object('channel_id', NEW.channel_id)::TEXT);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_notify_video_queue_insert ON video_queue;
CREATE TRIGGER trg_notify_video_queue_insert
AFTER INSERT ON video_queue
FOR EACH ROW EXECUTE FUNCTION notify_video_queue_update();

-- Column list covers every field the stream payload derives from a mutable
-- column. is_vertical / video_id / video_type / requested_by are also in the
-- payload but are set once at INSERT and never UPDATEd today — omitted here,
-- but if a future migration makes them mutable, add them to both this list
-- and the WHEN clause below.
DROP TRIGGER IF EXISTS trg_notify_video_queue_update ON video_queue;
CREATE TRIGGER trg_notify_video_queue_update
AFTER UPDATE OF status, priority, created_at, started_at, duration_seconds, title ON video_queue
FOR EACH ROW
WHEN (
    OLD.status IS DISTINCT FROM NEW.status
    OR OLD.priority IS DISTINCT FROM NEW.priority
    OR OLD.created_at IS DISTINCT FROM NEW.created_at
    OR OLD.started_at IS DISTINCT FROM NEW.started_at
    OR OLD.duration_seconds IS DISTINCT FROM NEW.duration_seconds
    OR OLD.title IS DISTINCT FROM NEW.title
)
EXECUTE FUNCTION notify_video_queue_update();
