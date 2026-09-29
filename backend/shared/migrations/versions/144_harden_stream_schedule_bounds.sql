-- Migration 144: publish-ready bounds for newly created or modified schedule data.
-- Existing out-of-range rows remain readable: NOT VALID constraints avoid silently
-- truncating or deleting legacy data while still rejecting new invalid writes.

ALTER TABLE stream_schedules
    DROP CONSTRAINT stream_schedules_duration_minutes_check;

ALTER TABLE stream_schedules
    ADD CONSTRAINT chk_stream_schedules_duration_publishable
    CHECK (duration_minutes BETWEEN 30 AND 1380) NOT VALID;

ALTER TABLE stream_schedule_segments
    ADD CONSTRAINT chk_stream_schedule_segments_title_publishable
    CHECK (char_length(title_template) <= 140) NOT VALID;

CREATE FUNCTION fn_validate_stream_schedule_segment_offset()
RETURNS TRIGGER AS $$
DECLARE
    schedule_duration INT;
BEGIN
    SELECT duration_minutes INTO schedule_duration
    FROM stream_schedules
    WHERE id = NEW.schedule_id;

    IF schedule_duration IS NULL OR NEW.offset_minutes >= schedule_duration THEN
        RAISE EXCEPTION 'stream schedule segment offset is outside schedule duration'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_stream_schedule_segment_offset
    BEFORE INSERT OR UPDATE OF schedule_id, offset_minutes
    ON stream_schedule_segments
    FOR EACH ROW EXECUTE FUNCTION fn_validate_stream_schedule_segment_offset();

CREATE FUNCTION fn_validate_stream_schedule_duration_segments()
RETURNS TRIGGER AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM stream_schedule_segments
        WHERE schedule_id = NEW.id
          AND offset_minutes >= NEW.duration_minutes
    ) THEN
        RAISE EXCEPTION 'stream schedule duration excludes an existing segment'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_stream_schedule_duration_segments
    BEFORE UPDATE OF duration_minutes
    ON stream_schedules
    FOR EACH ROW EXECUTE FUNCTION fn_validate_stream_schedule_duration_segments();
