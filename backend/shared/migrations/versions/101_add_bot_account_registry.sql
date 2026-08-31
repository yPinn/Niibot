-- 101: Tenant-private bot account registry and one-time OAuth invitations.
--
-- Credentials remain in the versioned `tokens` table.  This migration stores
-- only account metadata, tenant mappings, hashed invitation material, and an
-- immutable tenant audit trail.

CREATE TABLE bot_accounts (
    platform_user_id  TEXT PRIMARY KEY,
    platform          TEXT NOT NULL DEFAULT 'twitch'
                      CHECK (platform = 'twitch'),
    identity_id       UUID REFERENCES identities(id) ON DELETE SET NULL,
    login             TEXT NOT NULL,
    display_name      TEXT NOT NULL,
    avatar            TEXT,
    is_system_default BOOLEAN NOT NULL DEFAULT FALSE,
    requires_reauth   BOOLEAN NOT NULL DEFAULT FALSE,
    last_validated_at TIMESTAMPTZ,
    revoked_at        TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_bot_accounts_system_default
    ON bot_accounts (is_system_default)
    WHERE is_system_default;

CREATE INDEX idx_bot_accounts_identity_id
    ON bot_accounts (identity_id)
    WHERE identity_id IS NOT NULL;

DROP TRIGGER IF EXISTS trg_bot_accounts_updated_at ON bot_accounts;
CREATE TRIGGER trg_bot_accounts_updated_at
    BEFORE UPDATE ON bot_accounts
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

CREATE TABLE bot_oauth_invites (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id             TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    purpose                TEXT NOT NULL
                           CHECK (purpose IN ('link_new', 'reauthorize', 'system_default_reset')),
    expected_bot_user_id   TEXT REFERENCES bot_accounts(platform_user_id) ON DELETE CASCADE,
    created_by_user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
    public_token_hash      CHAR(64) NOT NULL UNIQUE,
    state_nonce_hash       CHAR(64) NOT NULL,
    status                 TEXT NOT NULL DEFAULT 'pending'
                           CHECK (status IN ('pending', 'authorized', 'declined', 'expired')),
    expires_at             TIMESTAMPTZ NOT NULL,
    consumed_at            TIMESTAMPTZ,
    authorized_bot_user_id TEXT REFERENCES bot_accounts(platform_user_id) ON DELETE SET NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (expires_at > created_at),
    CHECK ((status = 'pending' AND consumed_at IS NULL)
        OR (status <> 'pending' AND consumed_at IS NOT NULL))
);

CREATE INDEX idx_bot_oauth_invites_channel_created
    ON bot_oauth_invites (channel_id, created_at DESC);

CREATE INDEX idx_bot_oauth_invites_pending_expiry
    ON bot_oauth_invites (expires_at)
    WHERE status = 'pending';

DROP TRIGGER IF EXISTS trg_bot_oauth_invites_updated_at ON bot_oauth_invites;
CREATE TRIGGER trg_bot_oauth_invites_updated_at
    BEFORE UPDATE ON bot_oauth_invites
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

CREATE TABLE channel_bot_accounts (
    channel_id          TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    bot_user_id         TEXT NOT NULL REFERENCES bot_accounts(platform_user_id) ON DELETE CASCADE,
    linked_by_user_id   UUID REFERENCES users(id) ON DELETE SET NULL,
    linked_via_invite_id UUID REFERENCES bot_oauth_invites(id) ON DELETE SET NULL,
    linked_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (channel_id, bot_user_id)
);

CREATE INDEX idx_channel_bot_accounts_bot_user_id
    ON channel_bot_accounts (bot_user_id);

CREATE TABLE tenant_audit_events (
    id                       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel_id               TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    actor_user_id            UUID REFERENCES users(id) ON DELETE SET NULL,
    external_actor_user_id   TEXT,
    event_type               TEXT NOT NULL,
    target_type              TEXT,
    target_id                TEXT,
    metadata                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tenant_audit_events_channel_created
    ON tenant_audit_events (channel_id, created_at DESC);

-- Policies are staged now and activated table-by-table after the application
-- starts binding app.current_channel_id on every tenant-scoped transaction.
CREATE POLICY p_bot_oauth_invites_tenant ON bot_oauth_invites
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));

CREATE POLICY p_channel_bot_accounts_tenant ON channel_bot_accounts
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));

CREATE POLICY p_tenant_audit_events_tenant ON tenant_audit_events
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));
