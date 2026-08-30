-- Add optimistic concurrency and make published theme revisions fully immutable.

ALTER TABLE community_overlay_profiles
    ADD COLUMN draft_version BIGINT NOT NULL DEFAULT 1 CHECK (draft_version > 0);

DROP TRIGGER trg_community_overlay_revisions_immutable ON community_overlay_revisions;

CREATE TRIGGER trg_community_overlay_revisions_immutable
    BEFORE UPDATE OR DELETE ON community_overlay_revisions
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_community_overlay_revision_update();
