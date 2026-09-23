-- Additive lifecycle metadata for Twitch credentials and revocable dashboard sessions.
-- Existing credentials remain usable and receive their first health check after deploy.

ALTER TABLE tokens
    ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_validated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS invalidated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS validation_error_code TEXT;

ALTER TABLE tokens
    DROP CONSTRAINT IF EXISTS tokens_validation_error_code_check;

ALTER TABLE tokens
    ADD CONSTRAINT tokens_validation_error_code_check
    CHECK (
        validation_error_code IS NULL OR validation_error_code IN (
            'missing_scopes',
            'invalid_token',
            'identity_mismatch',
            'client_mismatch',
            'provider_unavailable',
            'refresh_failed',
            'revoked'
        )
    );

CREATE INDEX IF NOT EXISTS idx_tokens_authorization_check_due
    ON tokens (last_checked_at NULLS FIRST)
    WHERE invalidated_at IS NULL;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS session_version BIGINT NOT NULL DEFAULT 1;

ALTER TABLE users
    DROP CONSTRAINT IF EXISTS users_session_version_positive;

ALTER TABLE users
    ADD CONSTRAINT users_session_version_positive CHECK (session_version > 0);

COMMENT ON COLUMN tokens.last_checked_at IS
    'Last attempt to validate this Twitch credential, including provider outages';
COMMENT ON COLUMN tokens.last_validated_at IS
    'Last time Twitch confirmed identity, client, and required scopes';
COMMENT ON COLUMN tokens.invalidated_at IS
    'Definite local invalidation; transient provider outages leave this NULL';
COMMENT ON COLUMN users.session_version IS
    'Increment to invalidate every dashboard JWT previously issued to this user';
