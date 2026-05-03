CREATE TABLE viewer_attendance_streaks (
    channel_id      TEXT NOT NULL,
    user_id         TEXT NOT NULL,
    streak_count    INT  NOT NULL DEFAULT 1,
    last_session_id INT  REFERENCES stream_sessions(id) ON DELETE SET NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (channel_id, user_id)
);

CREATE INDEX idx_viewer_attendance_streaks_channel
    ON viewer_attendance_streaks (channel_id);
