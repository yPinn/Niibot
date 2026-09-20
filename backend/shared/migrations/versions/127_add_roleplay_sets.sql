-- Tenant-owned Canon Role-play drafts and immutable published revisions.
-- Runtime uses only compiled artifacts; authoring JSON cannot control provider policy.

CREATE TABLE roleplay_sets (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id            TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    name                  TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 100),
    draft                 JSONB NOT NULL CHECK (jsonb_typeof(draft) = 'object'),
    draft_version         BIGINT NOT NULL DEFAULT 1 CHECK (draft_version > 0),
    published_revision_id BIGINT,
    archived_at           TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (channel_id, id)
);

CREATE INDEX idx_roleplay_sets_channel_active
    ON roleplay_sets (channel_id, created_at, id)
    WHERE archived_at IS NULL;

CREATE TRIGGER trg_roleplay_sets_updated_at
    BEFORE UPDATE ON roleplay_sets
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

CREATE TABLE roleplay_revisions (
    id               BIGSERIAL PRIMARY KEY,
    channel_id       TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    roleplay_set_id  UUID NOT NULL,
    revision_number  INT NOT NULL CHECK (revision_number > 0),
    schema_version   SMALLINT NOT NULL CHECK (schema_version > 0),
    compiler_version INT NOT NULL CHECK (compiler_version > 0),
    source_snapshot  JSONB NOT NULL CHECK (jsonb_typeof(source_snapshot) = 'object'),
    capsule           TEXT NOT NULL CHECK (char_length(capsule) BETWEEN 1 AND 900),
    compact_capsule   TEXT NOT NULL CHECK (char_length(compact_capsule) BETWEEN 1 AND 500),
    content_digest    TEXT NOT NULL CHECK (content_digest ~ '^[0-9a-f]{64}$'),
    published_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (roleplay_set_id, revision_number),
    UNIQUE (channel_id, id),
    UNIQUE (channel_id, roleplay_set_id, id),
    FOREIGN KEY (channel_id, roleplay_set_id)
        REFERENCES roleplay_sets(channel_id, id) ON DELETE CASCADE
);

CREATE INDEX idx_roleplay_revisions_set
    ON roleplay_revisions (channel_id, roleplay_set_id, revision_number DESC);

ALTER TABLE roleplay_sets
    ADD CONSTRAINT fk_roleplay_sets_published_revision
    FOREIGN KEY (channel_id, id, published_revision_id)
    REFERENCES roleplay_revisions(channel_id, roleplay_set_id, id)
    DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ai_settings
    ADD COLUMN assistant_mode TEXT NOT NULL DEFAULT 'persona',
    ADD COLUMN active_roleplay_revision_id BIGINT,
    ADD CONSTRAINT ai_settings_assistant_mode_check
        CHECK (assistant_mode IN ('persona', 'roleplay')),
    ADD CONSTRAINT ai_settings_mode_revision_check
        CHECK (
            (assistant_mode = 'persona' AND active_roleplay_revision_id IS NULL)
            OR
            (assistant_mode = 'roleplay' AND active_roleplay_revision_id IS NOT NULL)
        ),
    ADD CONSTRAINT fk_ai_settings_active_roleplay_revision
        FOREIGN KEY (channel_id, active_roleplay_revision_id)
        REFERENCES roleplay_revisions(channel_id, id)
        DEFERRABLE INITIALLY DEFERRED;

CREATE OR REPLACE FUNCTION fn_prevent_roleplay_revision_mutation()
RETURNS TRIGGER AS $$
BEGIN
    -- Preserve normal channel/set lifecycle cascades while rejecting direct mutation.
    IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'role-play revisions are immutable';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_roleplay_revisions_immutable
    BEFORE UPDATE OR DELETE ON roleplay_revisions
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_roleplay_revision_mutation();

CREATE POLICY p_roleplay_sets_tenant ON roleplay_sets
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));

CREATE POLICY p_roleplay_revisions_tenant ON roleplay_revisions
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));

-- RLS activation is deliberately omitted until the existing BYPASSRLS rollout is complete.
