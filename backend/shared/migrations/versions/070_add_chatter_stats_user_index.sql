-- Enable fast cross-channel user lookups for overlap analysis
CREATE INDEX IF NOT EXISTS idx_chatter_stats_user_id
    ON chatter_stats(user_id);
