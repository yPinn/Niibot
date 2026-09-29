-- Freeze the check-in clock when a live session is observed. VOD-only rows keep
-- the fail-closed defaults and therefore never create a streak obligation.
ALTER TABLE stream_sessions
    ADD COLUMN checkin_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN checkin_timezone TEXT,
    ADD COLUMN checkin_broadcast_day DATE;

ALTER TABLE stream_sessions
    ADD CONSTRAINT chk_stream_sessions_checkin_day_snapshot
    CHECK (
        NOT checkin_eligible
        OR (checkin_timezone IS NOT NULL AND checkin_broadcast_day IS NOT NULL)
    ) NOT VALID;

WITH observed_sessions AS (
    SELECT
        session.id,
        COALESCE(settings.timezone, 'Asia/Taipei') AS timezone
    FROM stream_sessions AS session
    LEFT JOIN checkin_settings AS settings
      ON settings.channel_id = session.channel_id
    WHERE session.ended_at IS NULL
       OR session.attendance_snapshot_count > 0
       OR EXISTS (
            SELECT 1 FROM stream_events AS event WHERE event.session_id = session.id
       )
       OR EXISTS (
            SELECT 1 FROM viewer_checkins AS checkin WHERE checkin.session_id = session.id
       )
)
UPDATE stream_sessions AS session
SET checkin_eligible = TRUE,
    checkin_timezone = observed.timezone,
    checkin_broadcast_day = (session.started_at AT TIME ZONE observed.timezone)::DATE
FROM observed_sessions AS observed
WHERE observed.id = session.id;

ALTER TABLE stream_sessions
    VALIDATE CONSTRAINT chk_stream_sessions_checkin_day_snapshot;

CREATE INDEX idx_stream_sessions_checkin_days
    ON stream_sessions (channel_id, checkin_broadcast_day DESC, id DESC)
    WHERE checkin_eligible;
