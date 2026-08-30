-- 090: Dedicated read-only role for the admin DB console (Monitor → DB tab).
--
-- ## Why
-- The admin DB console (`POST /api/admin/db/query`) runs owner-supplied SELECTs
-- on the application's asyncpg pool — a connection that owns full write access
-- to every table. The only guardrail was `transaction(readonly=True)`. That
-- blocks writes, but does nothing about *reading* secrets:
--   * tokens.token / tokens.refresh          — live Twitch OAuth tokens
--   * user_payment_configs.hash_key / hash_iv — ECPay signing keys
--   * activation_codes.code_hash / code_plain — activation codes
-- If the owner's session cookie ever leaked, `SELECT * FROM tokens` would hand
-- over every linked user's credentials.
--
-- ## What this does
-- Creates a NOLOGIN role `niibot_db_console` with SELECT on everything EXCEPT
-- those columns (column-level GRANT — an alias like `SELECT hash_key AS x` is
-- rejected by Postgres itself, not by app-layer string matching). The API sets
-- `SET LOCAL ROLE niibot_db_console` inside the read-only transaction before
-- running the query, and drives the schema browser off `has_column_privilege`
-- for this same role, so protected columns are not even listed.
--
-- ## Fail-closed
-- Wrapped in a DO block that downgrades a privilege error to a WARNING: on a
-- managed Postgres where the migration user cannot CREATE ROLE, the rest of the
-- migration chain must still apply. When the role is absent the API's
-- `SET LOCAL ROLE` errors and the console returns a "run migration 090" message
-- rather than falling back to the privileged connection.
--
-- Note: migration 083's RLS policies are currently disabled. If they are ever
-- enabled, this role is subject to them too — which is the desired behaviour.

DO $$
BEGIN
    -- 1. The role itself. NOLOGIN: only reachable via SET ROLE from the app user.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'niibot_db_console') THEN
        CREATE ROLE niibot_db_console NOLOGIN;
    END IF;

    -- 2. Baseline: read everything in `public`.
    GRANT USAGE ON SCHEMA public TO niibot_db_console;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO niibot_db_console;

    -- 3. Future tables/views created by the migration user are covered too.
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT SELECT ON TABLES TO niibot_db_console;

    -- 4. Revoke the three secret-bearing tables wholesale, then re-grant only
    --    the safe columns. REVOKE + column GRANT = deny on everything unlisted.
    REVOKE SELECT ON tokens FROM niibot_db_console;
    GRANT SELECT (user_id, token_type, scopes, requires_reauth, identity_id,
                  created_at, updated_at)
        ON tokens TO niibot_db_console;

    REVOKE SELECT ON user_payment_configs FROM niibot_db_console;
    GRANT SELECT (user_id, platform, merchant_id, min_amount,
                  media_share_enabled, enabled, created_at, updated_at)
        ON user_payment_configs TO niibot_db_console;

    REVOKE SELECT ON activation_codes FROM niibot_db_console;
    GRANT SELECT (id, kind, status, platform, platform_user_id, expires_at,
                  used_at, used_by_user_id, issued_at, issued_by_user_id,
                  redemption_id, channel_id, reward_cost, attempt_count)
        ON activation_codes TO niibot_db_console;

    -- 5. The API's login role must be a member to `SET ROLE` to it. In every
    --    deployed environment the API and the migration run as the same
    --    POSTGRES_USER, so CURRENT_USER is that role.
    EXECUTE format('GRANT niibot_db_console TO %I', CURRENT_USER);

EXCEPTION
    WHEN insufficient_privilege THEN
        RAISE WARNING
            'migration 090: insufficient privilege to provision niibot_db_console; '
            'the admin DB console will stay disabled until a superuser applies it';
END
$$;
