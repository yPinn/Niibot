-- Migration 124: Track when a broadcaster was last notified about a missing
-- OAuth scope, so load_tokens() can cool down repeat warnings across restarts
-- instead of re-logging the same unresolved reauth requirement every deploy.

ALTER TABLE tokens ADD COLUMN IF NOT EXISTS reauth_notified_at TIMESTAMPTZ;
