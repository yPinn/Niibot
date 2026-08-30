-- A stream is eligible for attendance inference only after at least one
-- complete /helix/chat/chatters snapshot. Zero means observation is unknown.
ALTER TABLE stream_sessions
    ADD COLUMN IF NOT EXISTS attendance_snapshot_count INT NOT NULL DEFAULT 0;

ALTER TABLE stream_sessions
    DROP CONSTRAINT IF EXISTS chk_stream_sessions_attendance_snapshot_count;

ALTER TABLE stream_sessions
    ADD CONSTRAINT chk_stream_sessions_attendance_snapshot_count
    CHECK (attendance_snapshot_count >= 0) NOT VALID;

ALTER TABLE stream_sessions
    VALIDATE CONSTRAINT chk_stream_sessions_attendance_snapshot_count;

CREATE INDEX IF NOT EXISTS idx_stream_sessions_attendance_eligible
    ON stream_sessions (channel_id, started_at DESC, id DESC)
    WHERE attendance_snapshot_count > 0;
