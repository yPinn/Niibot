-- Migration 114: Also notify the bot when a broadcaster clears requires_reauth,
-- not only when scopes change.
--
-- Migration 069's trigger only fired pg_notify('token_reauth', ...) when
-- NEW.scopes IS DISTINCT FROM OLD.scopes. A broadcaster who re-authorizes with
-- the SAME scope set they already had (the common case — the requested scope
-- list rarely changes) writes a fresh working token to `tokens`, but the
-- trigger stays silent: the running bot process never hears about it, keeps
-- serving the old dead token from its in-process cache / SubscriptionManager
-- state, and the channel stays broken until the bot process happens to
-- restart. Now also fire when requires_reauth flips TRUE -> FALSE, which is
-- exactly the signal that a previously-flagged token became valid again.

CREATE OR REPLACE FUNCTION fn_notify_token_reauth()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    IF NEW.token_type = 'broadcaster' AND (
        NEW.scopes IS DISTINCT FROM OLD.scopes
        OR (OLD.requires_reauth AND NOT NEW.requires_reauth)
    ) THEN
        PERFORM pg_notify('token_reauth', json_build_object(
            'user_id', NEW.user_id
        )::text);
    END IF;
    RETURN NEW;
END;
$$;
