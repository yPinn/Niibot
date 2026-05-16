-- Migration 062: Add (channel_id, user_id) index on stream_events
-- Covers viewer profile queries that filter by both channel and user with no prior index.
CREATE INDEX IF NOT EXISTS idx_events_channel_user
    ON stream_events(channel_id, user_id);
