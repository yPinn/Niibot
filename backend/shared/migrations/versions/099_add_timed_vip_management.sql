-- Durable, tenant-scoped timed VIP rules and reconciliation state.
-- RLS policies are installed but intentionally left disabled, matching migration 083.

CREATE TABLE vip_channel_settings (
    channel_id          TEXT PRIMARY KEY REFERENCES channels(channel_id) ON DELETE CASCADE,
    slot_limit          INTEGER CHECK (slot_limit IS NULL OR slot_limit BETWEEN 1 AND 500),
    tracking_started_at TIMESTAMPTZ,
    last_full_sync_at   TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_vip_channel_settings_updated_at
    BEFORE UPDATE ON vip_channel_settings
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

CREATE TABLE vip_reward_rules (
    id                   BIGSERIAL PRIMARY KEY,
    channel_id           TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    reward_id            TEXT NOT NULL CHECK (char_length(reward_id) BETWEEN 1 AND 128),
    reward_name_snapshot TEXT NOT NULL
                         CHECK (char_length(reward_name_snapshot) BETWEEN 1 AND 256),
    duration_months      SMALLINT,
    is_permanent         BOOLEAN NOT NULL DEFAULT FALSE,
    enabled              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (channel_id, reward_id),
    UNIQUE (channel_id, id),
    CHECK (
        (is_permanent AND duration_months IS NULL)
        OR (
            NOT is_permanent
            AND duration_months IS NOT NULL
            AND duration_months BETWEEN 1 AND 120
        )
    )
);

CREATE INDEX idx_vip_reward_rules_channel_enabled
    ON vip_reward_rules (channel_id, enabled, id);

CREATE TRIGGER trg_vip_reward_rules_updated_at
    BEFORE UPDATE ON vip_reward_rules
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

CREATE TABLE vip_entitlements (
    id                  BIGSERIAL PRIMARY KEY,
    channel_id          TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    user_id             TEXT NOT NULL CHECK (char_length(user_id) BETWEEN 1 AND 128),
    user_login          TEXT NOT NULL CHECK (char_length(user_login) BETWEEN 1 AND 128),
    display_name        TEXT CHECK (display_name IS NULL OR char_length(display_name) <= 128),
    source              TEXT NOT NULL
                        CHECK (source IN ('external_baseline', 'external_event', 'managed')),
    status              TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'expired', 'removed_external', 'released')),
    granted_at          TIMESTAMPTZ,
    expires_at          TIMESTAMPTZ,
    is_permanent        BOOLEAN NOT NULL DEFAULT FALSE,
    last_reward_rule_id BIGINT,
    last_synced_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expiry_claimed_at   TIMESTAMPTZ,
    version             BIGINT NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (channel_id, user_id),
    UNIQUE (channel_id, id),
    FOREIGN KEY (channel_id, last_reward_rule_id)
        REFERENCES vip_reward_rules(channel_id, id) ON DELETE RESTRICT,
    CHECK (expires_at IS NULL OR granted_at IS NULL OR expires_at > granted_at),
    CHECK (NOT is_permanent OR expires_at IS NULL)
);

CREATE INDEX idx_vip_entitlements_channel_status
    ON vip_entitlements (channel_id, status, source, user_id);

CREATE INDEX idx_vip_entitlements_due
    ON vip_entitlements (expires_at, channel_id, id)
    WHERE status = 'active'
      AND source = 'managed'
      AND NOT is_permanent
      AND expires_at IS NOT NULL;

CREATE TRIGGER trg_vip_entitlements_updated_at
    BEFORE UPDATE ON vip_entitlements
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

CREATE TABLE vip_redemption_events (
    id                         BIGSERIAL PRIMARY KEY,
    channel_id                 TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    redemption_id              TEXT NOT NULL
                               CHECK (char_length(redemption_id) BETWEEN 1 AND 128),
    rule_id                    BIGINT,
    reward_id                  TEXT NOT NULL CHECK (char_length(reward_id) BETWEEN 1 AND 128),
    reward_name_snapshot       TEXT NOT NULL
                               CHECK (char_length(reward_name_snapshot) BETWEEN 1 AND 256),
    user_id                    TEXT NOT NULL CHECK (char_length(user_id) BETWEEN 1 AND 128),
    user_login                 TEXT NOT NULL CHECK (char_length(user_login) BETWEEN 1 AND 128),
    display_name               TEXT CHECK (
        display_name IS NULL OR char_length(display_name) <= 128
    ),
    duration_months_snapshot   SMALLINT,
    is_permanent_snapshot      BOOLEAN NOT NULL DEFAULT FALSE,
    status                     TEXT NOT NULL DEFAULT 'received' CHECK (
        status IN (
            'received',
            'granting',
            'granted',
            'extended',
            'adopted',
            'kept_external',
            'needs_review_external_vip',
            'capacity_full',
            'moderator_conflict',
            'not_initialized',
            'failed'
        )
    ),
    error_code                 TEXT CHECK (
        error_code IS NULL OR char_length(error_code) BETWEEN 1 AND 80
    ),
    occurred_at                TIMESTAMPTZ NOT NULL,
    processed_at               TIMESTAMPTZ,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (channel_id, redemption_id),
    FOREIGN KEY (channel_id, rule_id)
        REFERENCES vip_reward_rules(channel_id, id) ON DELETE RESTRICT,
    CHECK (
        (is_permanent_snapshot AND duration_months_snapshot IS NULL)
        OR (
            NOT is_permanent_snapshot
            AND duration_months_snapshot IS NOT NULL
            AND duration_months_snapshot BETWEEN 1 AND 120
        )
    )
);

CREATE INDEX idx_vip_redemption_events_channel_time
    ON vip_redemption_events (channel_id, occurred_at DESC, id DESC);

CREATE INDEX idx_vip_redemption_events_review
    ON vip_redemption_events (channel_id, status, occurred_at DESC)
    WHERE status IN (
        'needs_review_external_vip',
        'capacity_full',
        'moderator_conflict',
        'failed'
    );

-- Preserve the existing single VIP action as the first timed rule. Future rules
-- live only in vip_reward_rules and can bind multiple reward ids per channel.
INSERT INTO vip_reward_rules (
    channel_id,
    reward_id,
    reward_name_snapshot,
    duration_months,
    is_permanent,
    enabled
)
SELECT
    channel_id,
    reward_id,
    reward_name,
    3,
    FALSE,
    enabled
FROM redemption_configs
WHERE action_type = 'vip'
  AND reward_id IS NOT NULL
ON CONFLICT (channel_id, reward_id) DO NOTHING;

CREATE POLICY p_vip_channel_settings_tenant ON vip_channel_settings
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));

CREATE POLICY p_vip_reward_rules_tenant ON vip_reward_rules
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));

CREATE POLICY p_vip_entitlements_tenant ON vip_entitlements
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));

CREATE POLICY p_vip_redemption_events_tenant ON vip_redemption_events
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));

-- RLS activation is deliberately omitted until the existing BYPASSRLS rollout is complete.
