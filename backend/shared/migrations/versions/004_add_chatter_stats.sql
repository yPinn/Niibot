-- ============================================
-- Add chatter_stats table for tracking chat message counts per session
-- ============================================

CREATE TABLE IF NOT EXISTS chatter_stats (
    id             SERIAL PRIMARY KEY,
    session_id     INT  NOT NULL REFERENCES stream_sessions(id) ON DELETE CASCADE,
    channel_id     TEXT NOT NULL,
    user_id        TEXT NOT NULL,
    username       TEXT NOT NULL,
    message_count  INT  DEFAULT 1,
    last_message_at TIMESTAMPTZ NOT NULL,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(session_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_chatter_channel_time ON chatter_stats(channel_id, last_message_at DESC);
CREATE INDEX IF NOT EXISTS idx_chatter_session      ON chatter_stats(session_id, message_count DESC);
