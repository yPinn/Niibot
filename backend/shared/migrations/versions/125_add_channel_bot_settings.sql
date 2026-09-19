-- 125: Per-channel bot sender selection state.
--
-- No row for a channel means "use the system-default bot" — every reader must
-- LEFT JOIN and COALESCE rather than assume a row exists. The runtime writes
-- back active_bot_user_id/acked_version itself once a switch completes, so
-- change notification is sent explicitly by the API on desired-writes (see
-- bot_selection_service.py), not via a row trigger — a trigger would also
-- fire on the runtime's own confirmation write and loop back on itself.

CREATE TABLE channel_bot_settings (
    channel_id          TEXT PRIMARY KEY REFERENCES channels(channel_id) ON DELETE CASCADE,
    desired_bot_user_id TEXT REFERENCES bot_accounts(platform_user_id) ON DELETE RESTRICT,
    active_bot_user_id  TEXT REFERENCES bot_accounts(platform_user_id) ON DELETE RESTRICT,
    selection_version   BIGINT NOT NULL DEFAULT 0,
    acked_version       BIGINT NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'switching', 'failed')),
    last_error_code     TEXT,
    updated_by_user_id  UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_channel_bot_settings_unsettled
    ON channel_bot_settings (status)
    WHERE status <> 'active';

CREATE INDEX idx_channel_bot_settings_active_bot
    ON channel_bot_settings (active_bot_user_id)
    WHERE active_bot_user_id IS NOT NULL;

CREATE INDEX idx_channel_bot_settings_desired_bot
    ON channel_bot_settings (desired_bot_user_id)
    WHERE desired_bot_user_id IS NOT NULL;

DROP TRIGGER IF EXISTS trg_channel_bot_settings_updated_at ON channel_bot_settings;
CREATE TRIGGER trg_channel_bot_settings_updated_at
    BEFORE UPDATE ON channel_bot_settings
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

-- Staged, not enabled — same convention as migration 101.
CREATE POLICY p_channel_bot_settings_tenant ON channel_bot_settings
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));
