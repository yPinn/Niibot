-- Scope every overlay theme draft and immutable revision to one display block.
-- Existing installations only contain the check-in renderer, so the default
-- safely backfills all current rows into the `checkin` block.

ALTER TABLE community_overlay_profiles
    DROP CONSTRAINT fk_community_overlay_profiles_published_revision;

ALTER TABLE community_overlay_profiles
    ADD COLUMN block_type TEXT NOT NULL DEFAULT 'checkin'
        CHECK (block_type ~ '^[a-z][a-z0-9-]{0,31}$');

ALTER TABLE community_overlay_revisions
    ADD COLUMN block_type TEXT NOT NULL DEFAULT 'checkin'
        CHECK (block_type ~ '^[a-z][a-z0-9-]{0,31}$');

ALTER TABLE community_overlay_profiles
    DROP CONSTRAINT community_overlay_profiles_pkey,
    DROP CONSTRAINT community_overlay_profiles_renderer_check,
    DROP CONSTRAINT community_overlay_profiles_schema_version_check,
    ADD CHECK (renderer ~ '^[a-z][a-z0-9-]{0,63}$'),
    ADD CHECK (schema_version > 0),
    ADD PRIMARY KEY (channel_id, block_type);

ALTER TABLE community_overlay_revisions
    DROP CONSTRAINT community_overlay_revisions_channel_id_revision_number_key,
    DROP CONSTRAINT community_overlay_revisions_channel_id_id_key,
    DROP CONSTRAINT community_overlay_revisions_renderer_check,
    DROP CONSTRAINT community_overlay_revisions_schema_version_check,
    ADD CHECK (renderer ~ '^[a-z][a-z0-9-]{0,63}$'),
    ADD CHECK (schema_version > 0),
    ADD UNIQUE (channel_id, block_type, revision_number),
    ADD UNIQUE (channel_id, block_type, id);

ALTER TABLE community_overlay_profiles
    ADD CONSTRAINT fk_community_overlay_profiles_published_revision
    FOREIGN KEY (channel_id, block_type, published_revision_id)
    REFERENCES community_overlay_revisions(channel_id, block_type, id)
    DEFERRABLE INITIALLY DEFERRED;
