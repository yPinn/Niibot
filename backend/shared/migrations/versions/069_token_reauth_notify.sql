-- Migration 069: Notify bot when a broadcaster re-authorizes (scopes change)
-- Only fires on UPDATE when scopes column actually changes, so routine hourly
-- token refreshes (which preserve scopes) do NOT trigger this notification.

CREATE OR REPLACE FUNCTION fn_notify_token_reauth()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    IF NEW.token_type = 'broadcaster' AND (NEW.scopes IS DISTINCT FROM OLD.scopes) THEN
        PERFORM pg_notify('token_reauth', json_build_object(
            'user_id', NEW.user_id
        )::text);
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_tokens_notify_reauth ON tokens;
CREATE TRIGGER trg_tokens_notify_reauth
    AFTER UPDATE ON tokens
    FOR EACH ROW EXECUTE FUNCTION fn_notify_token_reauth();
