-- Composite index to support viewer profile lookups filtering by (channel_id, user_id).
-- Used by get_viewer_profile _stats query and get_viewer_session_attendance JOIN.

CREATE INDEX IF NOT EXISTS idx_chatter_channel_user
    ON chatter_stats (channel_id, user_id);
