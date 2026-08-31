-- Daily check-in ledger and durable community overlay delivery infrastructure.
-- RLS policies are installed but intentionally left disabled, matching migration 083.

CREATE TABLE checkin_settings (
    channel_id         TEXT PRIMARY KEY REFERENCES channels(channel_id) ON DELETE CASCADE,
    timezone           TEXT NOT NULL DEFAULT 'Asia/Taipei'
                       CHECK (char_length(timezone) BETWEEN 1 AND 64),
    success_template   TEXT NOT NULL DEFAULT '$(@user) 簽到成功，累積 $(count) 天！'
                       CHECK (char_length(success_template) BETWEEN 1 AND 500),
    duplicate_template TEXT NOT NULL DEFAULT '$(@user) 今天已經簽到過了！'
                       CHECK (char_length(duplicate_template) BETWEEN 1 AND 500),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_checkin_settings_updated_at
    BEFORE UPDATE ON checkin_settings
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

CREATE TABLE viewer_checkins (
    id           BIGSERIAL PRIMARY KEY,
    channel_id   TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    user_id      TEXT NOT NULL CHECK (char_length(user_id) BETWEEN 1 AND 128),
    username     TEXT NOT NULL CHECK (char_length(username) BETWEEN 1 AND 128),
    display_name TEXT CHECK (display_name IS NULL OR char_length(display_name) <= 128),
    checkin_date DATE NOT NULL,
    session_id   INT REFERENCES stream_sessions(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (channel_id, user_id, checkin_date)
);

CREATE INDEX idx_viewer_checkins_channel_date
    ON viewer_checkins (channel_id, checkin_date DESC, id DESC);

CREATE INDEX idx_viewer_checkins_channel_user
    ON viewer_checkins (channel_id, user_id, checkin_date DESC);

CREATE TABLE community_overlay_channels (
    channel_id TEXT PRIMARY KEY REFERENCES channels(channel_id) ON DELETE CASCADE,
    public_key UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    enabled    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_community_overlay_channels_updated_at
    BEFORE UPDATE ON community_overlay_channels
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

CREATE TABLE community_overlay_events (
    id                 BIGSERIAL PRIMARY KEY,
    channel_id         TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    event_type         TEXT NOT NULL CHECK (char_length(event_type) BETWEEN 1 AND 80),
    schema_version     SMALLINT NOT NULL CHECK (schema_version > 0),
    source             TEXT NOT NULL CHECK (source IN ('twitch', 'discord', 'api', 'system')),
    actor_user_id      TEXT CHECK (actor_user_id IS NULL OR char_length(actor_user_id) <= 128),
    actor_display_name TEXT CHECK (
        actor_display_name IS NULL OR char_length(actor_display_name) <= 128
    ),
    payload            JSONB NOT NULL DEFAULT '{}'::JSONB
                       CHECK (jsonb_typeof(payload) = 'object'),
    occurred_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at         TIMESTAMPTZ,
    idempotency_key    TEXT NOT NULL CHECK (char_length(idempotency_key) BETWEEN 1 AND 200),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (expires_at IS NULL OR expires_at > occurred_at),
    UNIQUE (channel_id, idempotency_key)
);

CREATE INDEX idx_community_overlay_events_cursor
    ON community_overlay_events (channel_id, id ASC);

CREATE INDEX idx_community_overlay_events_expiry
    ON community_overlay_events (expires_at)
    WHERE expires_at IS NOT NULL;

CREATE POLICY p_checkin_settings_tenant ON checkin_settings
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));

CREATE POLICY p_viewer_checkins_tenant ON viewer_checkins
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));

CREATE POLICY p_community_overlay_channels_tenant ON community_overlay_channels
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));

CREATE POLICY p_community_overlay_events_tenant ON community_overlay_events
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));

-- RLS activation is deliberately omitted until the existing BYPASSRLS rollout is complete.
