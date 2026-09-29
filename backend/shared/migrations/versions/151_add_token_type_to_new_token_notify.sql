-- Migration 151: include credential role in new-token notifications.
--
-- Token rows carry an explicit broadcaster or bot role. Runtime handlers must
-- not infer that role from mutable sender selection state, so every insertion
-- notification carries token_type. Application policy currently rejects an
-- identity entering both runtime roles at once.

CREATE OR REPLACE FUNCTION fn_notify_new_token()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    PERFORM pg_notify('new_token', json_build_object(
        'user_id', NEW.user_id,
        'token_type', NEW.token_type
    )::text);
    RETURN NEW;
END;
$$;
