-- Migration 044: Add 'cheer' as a valid event_type in stream_events
--
-- The original inline CHECK was auto-named stream_events_event_type_check by PostgreSQL.
-- We drop it (if it exists under that name) and recreate with 'cheer' included.
-- The DO block handles the edge case where the auto-name differs.
DO $$
DECLARE
    con_name TEXT;
BEGIN
    SELECT conname INTO con_name
    FROM pg_constraint
    WHERE conrelid = 'stream_events'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%event_type%';

    IF con_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE stream_events DROP CONSTRAINT %I', con_name);
    END IF;
END;
$$;

ALTER TABLE stream_events ADD CONSTRAINT stream_events_event_type_check
    CHECK (event_type IN ('follow', 'subscribe', 'raid', 'cheer'));
