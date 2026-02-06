-- Migration: 003_new_token_notify
-- Description: Add PostgreSQL NOTIFY trigger for new token insertions
-- This enables real-time detection of new users instead of polling

-- New token NOTIFY (for Twitch bot real-time new user detection)
-- Only triggers on INSERT (new user), not on UPDATE (token refresh)
CREATE OR REPLACE FUNCTION fn_notify_new_token()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('new_token', json_build_object(
        'user_id', NEW.user_id
    )::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tokens_notify_insert ON tokens;
CREATE TRIGGER trg_tokens_notify_insert
    AFTER INSERT ON tokens
    FOR EACH ROW EXECUTE FUNCTION fn_notify_new_token();
