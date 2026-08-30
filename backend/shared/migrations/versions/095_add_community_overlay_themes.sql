-- Tenant-owned draft themes and immutable published revisions for Community Overlay.
-- Existing public keys remain valid; channels without a profile use the application default.

CREATE TABLE community_overlay_profiles (
    channel_id            TEXT PRIMARY KEY REFERENCES channels(channel_id) ON DELETE CASCADE,
    renderer              TEXT NOT NULL DEFAULT 'checkin-card'
                          CHECK (renderer = 'checkin-card'),
    schema_version        SMALLINT NOT NULL DEFAULT 1 CHECK (schema_version = 1),
    draft_theme           JSONB NOT NULL
                          DEFAULT '{"surface_color":"#FFF7CF","accent_color":"#EF4D88","text_color":"#241B34","placement":"bottom-right","radius_px":24,"display_ms":5500,"motion":"standard"}'::JSONB
                          CHECK (jsonb_typeof(draft_theme) = 'object'),
    published_revision_id BIGINT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_community_overlay_profiles_updated_at
    BEFORE UPDATE ON community_overlay_profiles
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

CREATE TABLE community_overlay_revisions (
    id              BIGSERIAL PRIMARY KEY,
    channel_id      TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    revision_number INT NOT NULL CHECK (revision_number > 0),
    renderer        TEXT NOT NULL CHECK (renderer = 'checkin-card'),
    schema_version  SMALLINT NOT NULL CHECK (schema_version = 1),
    theme           JSONB NOT NULL CHECK (jsonb_typeof(theme) = 'object'),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (channel_id, revision_number),
    UNIQUE (channel_id, id)
);

ALTER TABLE community_overlay_profiles
    ADD CONSTRAINT fk_community_overlay_profiles_published_revision
    FOREIGN KEY (channel_id, published_revision_id)
    REFERENCES community_overlay_revisions(channel_id, id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE OR REPLACE FUNCTION fn_prevent_community_overlay_revision_update()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'community overlay revisions are immutable';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_community_overlay_revisions_immutable
    BEFORE UPDATE ON community_overlay_revisions
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_community_overlay_revision_update();

CREATE POLICY p_community_overlay_profiles_tenant ON community_overlay_profiles
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));

CREATE POLICY p_community_overlay_revisions_tenant ON community_overlay_revisions
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));

-- RLS activation is deliberately omitted until the existing BYPASSRLS rollout is complete.
