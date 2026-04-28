-- Add watch_seconds to chatter_stats for viewer watch-time tracking.
-- Populated by the bot's periodic /helix/chat/chatters polling loop.

ALTER TABLE chatter_stats
    ADD COLUMN IF NOT EXISTS watch_seconds INT NOT NULL DEFAULT 0;
