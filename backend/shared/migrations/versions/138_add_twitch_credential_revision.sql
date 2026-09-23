-- Monotonic generation for compare-and-set credential invalidation and
-- same-scope runtime hot reload. Existing rows remain valid at revision 1.

ALTER TABLE tokens
    ADD COLUMN IF NOT EXISTS credential_revision BIGINT NOT NULL DEFAULT 1;

ALTER TABLE tokens
    DROP CONSTRAINT IF EXISTS tokens_credential_revision_positive;

ALTER TABLE tokens
    ADD CONSTRAINT tokens_credential_revision_positive
    CHECK (credential_revision > 0);

COMMENT ON COLUMN tokens.credential_revision IS
    'Monotonic generation incremented whenever the encrypted OAuth pair changes';

-- A fresh OAuth pair must reach the running Twitch process even when its
-- granted scope set and requires_reauth flag are unchanged.
CREATE OR REPLACE FUNCTION fn_notify_token_reauth()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    IF NEW.token_type = 'broadcaster' AND (
        NEW.credential_revision IS DISTINCT FROM OLD.credential_revision
        OR NEW.scopes IS DISTINCT FROM OLD.scopes
        OR (OLD.requires_reauth AND NOT NEW.requires_reauth)
    ) THEN
        PERFORM pg_notify('token_reauth', json_build_object(
            'user_id', NEW.user_id,
            'credential_revision', NEW.credential_revision,
            'scopes_changed', NEW.scopes IS DISTINCT FROM OLD.scopes,
            'reauth_cleared', OLD.requires_reauth AND NOT NEW.requires_reauth
        )::text);
    END IF;
    RETURN NEW;
END;
$$;
