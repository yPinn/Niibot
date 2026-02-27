-- Migration 027: Allow 'dashboard' as a valid source in video_queue
--
-- The original inline CHECK was created without a name; PostgreSQL may
-- auto-generate a name like video_queue_source_check or video_queue_source_check1.
-- Use a DO block to find and drop it by querying pg_constraint directly.

DO $$
DECLARE
    _cname text;
BEGIN
    SELECT con.conname INTO _cname
    FROM pg_constraint con
    JOIN pg_class cls ON cls.oid = con.conrelid
    JOIN pg_attribute att ON att.attrelid = cls.oid
                         AND att.attnum = ANY(con.conkey)
    WHERE cls.relname = 'video_queue'
      AND con.contype  = 'c'
      AND att.attname  = 'source'
    LIMIT 1;

    IF _cname IS NOT NULL THEN
        EXECUTE format('ALTER TABLE video_queue DROP CONSTRAINT %I', _cname);
    END IF;
END $$;

ALTER TABLE video_queue
    ADD CONSTRAINT video_queue_source_check
    CHECK (source IN ('chat', 'redemption', 'dashboard'));
