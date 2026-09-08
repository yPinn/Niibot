-- Immutable collection catalog, versioned draw pools, and per-check-in draw ledger.
-- Official catalog rows are global; tenant-authored catalogs arrive in a later migration.

CREATE TABLE rarity_definition_revisions (
    id               BIGSERIAL PRIMARY KEY,
    rarity_key       TEXT NOT NULL CHECK (rarity_key ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
    revision_number  INT NOT NULL CHECK (revision_number > 0),
    display_name     TEXT NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 40),
    sort_rank        SMALLINT NOT NULL CHECK (sort_rank > 0),
    effect_intensity SMALLINT NOT NULL CHECK (effect_intensity BETWEEN 0 AND 100),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (rarity_key, revision_number),
    UNIQUE (id, rarity_key)
);

CREATE TABLE collection_sets (
    id              BIGSERIAL PRIMARY KEY,
    set_key         TEXT NOT NULL CHECK (set_key ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
    revision_number INT NOT NULL CHECK (revision_number > 0),
    display_name    TEXT NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 100),
    total_cards     SMALLINT NOT NULL CHECK (total_cards > 0),
    published_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (set_key, revision_number)
);

CREATE TABLE collection_cards (
    id                 BIGSERIAL PRIMARY KEY,
    set_id             BIGINT NOT NULL REFERENCES collection_sets(id) ON DELETE RESTRICT,
    card_key           TEXT NOT NULL CHECK (card_key ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
    card_number        SMALLINT NOT NULL CHECK (card_number > 0),
    rarity_revision_id BIGINT NOT NULL
                       REFERENCES rarity_definition_revisions(id) ON DELETE RESTRICT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (set_id, card_key),
    UNIQUE (set_id, card_number),
    UNIQUE (id, set_id)
);

CREATE TABLE collection_card_revisions (
    id              BIGSERIAL PRIMARY KEY,
    card_id         BIGINT NOT NULL REFERENCES collection_cards(id) ON DELETE RESTRICT,
    revision_number INT NOT NULL CHECK (revision_number > 0),
    display_name    TEXT NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 100),
    description     TEXT NOT NULL DEFAULT '' CHECK (char_length(description) <= 500),
    portrait_url    TEXT CHECK (
        portrait_url IS NULL OR (
            portrait_url LIKE '/images/collections/%'
            AND position('..' IN portrait_url) = 0
            AND char_length(portrait_url) <= 500
        )
    ),
    square_url      TEXT CHECK (
        square_url IS NULL OR (
            square_url LIKE '/images/collections/%'
            AND position('..' IN square_url) = 0
            AND char_length(square_url) <= 500
        )
    ),
    backdrop_url    TEXT CHECK (
        backdrop_url IS NULL OR (
            backdrop_url LIKE '/images/collections/%'
            AND position('..' IN backdrop_url) = 0
            AND char_length(backdrop_url) <= 500
        )
    ),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (card_id, revision_number),
    UNIQUE (id, card_id)
);

CREATE TABLE draw_pool_revisions (
    id                BIGSERIAL PRIMARY KEY,
    pool_key          TEXT NOT NULL CHECK (pool_key ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
    revision_number   INT NOT NULL CHECK (revision_number > 0),
    algorithm_version TEXT NOT NULL
                      CHECK (algorithm_version ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
    published_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (pool_key, revision_number),
    UNIQUE (id, algorithm_version)
);

CREATE TABLE draw_pool_rarity_weights (
    pool_revision_id   BIGINT NOT NULL
                       REFERENCES draw_pool_revisions(id) ON DELETE RESTRICT,
    rarity_revision_id BIGINT NOT NULL
                       REFERENCES rarity_definition_revisions(id) ON DELETE RESTRICT,
    weight             INT NOT NULL CHECK (weight > 0),
    PRIMARY KEY (pool_revision_id, rarity_revision_id)
);

CREATE TABLE draw_pool_entries (
    pool_revision_id BIGINT NOT NULL
                     REFERENCES draw_pool_revisions(id) ON DELETE RESTRICT,
    card_revision_id BIGINT NOT NULL,
    card_id          BIGINT NOT NULL,
    entry_order      INT NOT NULL CHECK (entry_order > 0),
    PRIMARY KEY (pool_revision_id, card_revision_id),
    UNIQUE (pool_revision_id, entry_order),
    UNIQUE (pool_revision_id, card_id),
    FOREIGN KEY (card_revision_id, card_id)
        REFERENCES collection_card_revisions(id, card_id) ON DELETE RESTRICT
);

CREATE TABLE collection_system_settings (
    singleton                 SMALLINT PRIMARY KEY DEFAULT 1 CHECK (singleton = 1),
    fallback_pool_revision_id BIGINT NOT NULL
                              REFERENCES draw_pool_revisions(id) ON DELETE RESTRICT,
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_collection_system_settings_updated_at
    BEFORE UPDATE ON collection_system_settings
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

CREATE TABLE channel_collection_settings (
    channel_id              TEXT PRIMARY KEY
                            REFERENCES channels(channel_id) ON DELETE CASCADE,
    active_pool_revision_id BIGINT REFERENCES draw_pool_revisions(id) ON DELETE RESTRICT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_channel_collection_settings_updated_at
    BEFORE UPDATE ON channel_collection_settings
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

ALTER TABLE viewer_checkins
    ADD CONSTRAINT uq_viewer_checkins_channel_user_id
    UNIQUE (channel_id, user_id, id);

CREATE TABLE viewer_card_draws (
    id                  BIGSERIAL PRIMARY KEY,
    channel_id          TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    user_id             TEXT NOT NULL CHECK (char_length(user_id) BETWEEN 1 AND 128),
    checkin_id          BIGINT NOT NULL,
    pool_revision_id    BIGINT NOT NULL,
    card_revision_id    BIGINT NOT NULL,
    algorithm_version   TEXT NOT NULL
                        CHECK (algorithm_version ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
    entropy             BYTEA NOT NULL CHECK (octet_length(entropy) = 16),
    rarity_roll         BIGINT NOT NULL,
    rarity_weight_total BIGINT NOT NULL CHECK (rarity_weight_total > 0),
    card_roll           BIGINT NOT NULL,
    card_bucket_size    INT NOT NULL CHECK (card_bucket_size > 0),
    drawn_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (checkin_id),
    CHECK (rarity_roll >= 0 AND rarity_roll < rarity_weight_total),
    CHECK (card_roll >= 0 AND card_roll < card_bucket_size),
    FOREIGN KEY (channel_id, user_id, checkin_id)
        REFERENCES viewer_checkins(channel_id, user_id, id)
        ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (pool_revision_id, algorithm_version)
        REFERENCES draw_pool_revisions(id, algorithm_version) ON DELETE RESTRICT,
    FOREIGN KEY (pool_revision_id, card_revision_id)
        REFERENCES draw_pool_entries(pool_revision_id, card_revision_id) ON DELETE RESTRICT
);

CREATE INDEX idx_viewer_card_draws_channel_user
    ON viewer_card_draws (channel_id, user_id, drawn_at DESC, id DESC);

CREATE INDEX idx_viewer_card_draws_channel_card
    ON viewer_card_draws (channel_id, card_revision_id, id DESC);

CREATE OR REPLACE FUNCTION fn_prevent_collection_revision_change()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION '% rows are immutable', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_rarity_definition_revisions_immutable
    BEFORE UPDATE OR DELETE ON rarity_definition_revisions
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_collection_revision_change();

CREATE TRIGGER trg_collection_card_revisions_immutable
    BEFORE UPDATE OR DELETE ON collection_card_revisions
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_collection_revision_change();

CREATE OR REPLACE FUNCTION fn_publish_collection_set_once()
RETURNS TRIGGER AS $$
DECLARE
    actual_card_count INT;
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.published_at IS NULL
       AND NEW.published_at IS NOT NULL
       AND NEW.id = OLD.id
       AND NEW.set_key = OLD.set_key
       AND NEW.revision_number = OLD.revision_number
       AND NEW.display_name = OLD.display_name
       AND NEW.total_cards = OLD.total_cards
       AND NEW.created_at = OLD.created_at THEN
        SELECT COUNT(*)
        INTO actual_card_count
        FROM collection_cards
        WHERE set_id = OLD.id;

        IF actual_card_count <> OLD.total_cards THEN
            RAISE EXCEPTION
                'collection set % requires % cards but has %',
                OLD.id,
                OLD.total_cards,
                actual_card_count;
        END IF;

        IF EXISTS (
            SELECT 1
            FROM collection_cards AS card
            WHERE card.set_id = OLD.id
              AND NOT EXISTS (
                  SELECT 1
                  FROM collection_card_revisions AS revision
                  WHERE revision.card_id = card.id
              )
        ) THEN
            RAISE EXCEPTION 'every card in collection set % requires a revision', OLD.id;
        END IF;

        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'collection set revisions are immutable after creation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_collection_sets_publish_once
    BEFORE UPDATE OR DELETE ON collection_sets
    FOR EACH ROW EXECUTE FUNCTION fn_publish_collection_set_once();

CREATE OR REPLACE FUNCTION fn_guard_collection_card_change()
RETURNS TRIGGER AS $$
DECLARE
    parent_published_at TIMESTAMPTZ;
BEGIN
    IF TG_OP = 'INSERT' THEN
        SELECT published_at
        INTO parent_published_at
        FROM collection_sets
        WHERE id = NEW.set_id
        FOR SHARE;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'collection set % does not exist', NEW.set_id;
        END IF;

        IF parent_published_at IS NOT NULL THEN
            RAISE EXCEPTION 'cannot add cards to a published collection set';
        END IF;
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'logical collection cards are immutable';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_collection_cards_immutable
    BEFORE INSERT OR UPDATE OR DELETE ON collection_cards
    FOR EACH ROW EXECUTE FUNCTION fn_guard_collection_card_change();

CREATE OR REPLACE FUNCTION fn_publish_draw_pool_once()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.published_at IS NULL
       AND NEW.published_at IS NOT NULL
       AND NEW.id = OLD.id
       AND NEW.pool_key = OLD.pool_key
       AND NEW.revision_number = OLD.revision_number
       AND NEW.algorithm_version = OLD.algorithm_version
       AND NEW.created_at = OLD.created_at THEN
        IF NOT EXISTS (
            SELECT 1
            FROM draw_pool_entries
            WHERE pool_revision_id = OLD.id
        ) THEN
            RAISE EXCEPTION 'draw pool % cannot be published without entries', OLD.id;
        END IF;

        IF EXISTS (
            SELECT 1
            FROM draw_pool_entries AS entry
            JOIN collection_card_revisions AS revision
              ON revision.id = entry.card_revision_id
            JOIN collection_cards AS card
              ON card.id = revision.card_id
            JOIN collection_sets AS collection_set
              ON collection_set.id = card.set_id
            WHERE entry.pool_revision_id = OLD.id
              AND collection_set.published_at IS NULL
        ) THEN
            RAISE EXCEPTION 'draw pool % contains a card from an unpublished set', OLD.id;
        END IF;

        IF EXISTS (
            SELECT 1
            FROM draw_pool_entries AS entry
            JOIN collection_card_revisions AS revision
              ON revision.id = entry.card_revision_id
            JOIN collection_cards AS card
              ON card.id = revision.card_id
            LEFT JOIN draw_pool_rarity_weights AS weight
              ON weight.pool_revision_id = entry.pool_revision_id
             AND weight.rarity_revision_id = card.rarity_revision_id
            WHERE entry.pool_revision_id = OLD.id
              AND weight.rarity_revision_id IS NULL
        ) THEN
            RAISE EXCEPTION 'every entry in draw pool % requires a rarity weight', OLD.id;
        END IF;

        IF EXISTS (
            SELECT 1
            FROM draw_pool_rarity_weights AS weight
            WHERE weight.pool_revision_id = OLD.id
              AND NOT EXISTS (
                  SELECT 1
                  FROM draw_pool_entries AS entry
                  JOIN collection_card_revisions AS revision
                    ON revision.id = entry.card_revision_id
                  JOIN collection_cards AS card
                    ON card.id = revision.card_id
                  WHERE entry.pool_revision_id = weight.pool_revision_id
                    AND card.rarity_revision_id = weight.rarity_revision_id
              )
        ) THEN
            RAISE EXCEPTION 'every rarity weight in draw pool % requires an entry', OLD.id;
        END IF;

        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'draw pool revisions are immutable after creation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_draw_pool_revisions_immutable
    BEFORE UPDATE OR DELETE ON draw_pool_revisions
    FOR EACH ROW EXECUTE FUNCTION fn_publish_draw_pool_once();

CREATE OR REPLACE FUNCTION fn_guard_draw_pool_member_change()
RETURNS TRIGGER AS $$
DECLARE
    selected_pool_id BIGINT;
    parent_published_at TIMESTAMPTZ;
    revision_card_id BIGINT;
BEGIN
    IF TG_OP = 'INSERT' THEN
        selected_pool_id := NEW.pool_revision_id;
        SELECT published_at
        INTO parent_published_at
        FROM draw_pool_revisions
        WHERE id = selected_pool_id
        FOR SHARE;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'draw pool % does not exist', selected_pool_id;
        END IF;

        IF parent_published_at IS NOT NULL THEN
            RAISE EXCEPTION 'cannot add entries to a published draw pool';
        END IF;

        IF TG_TABLE_NAME = 'draw_pool_entries' THEN
            SELECT card_id
            INTO revision_card_id
            FROM collection_card_revisions
            WHERE id = NEW.card_revision_id;

            IF NOT FOUND THEN
                RAISE EXCEPTION 'collection card revision % does not exist', NEW.card_revision_id;
            END IF;

            IF NEW.card_id IS NULL THEN
                NEW.card_id := revision_card_id;
            ELSIF NEW.card_id <> revision_card_id THEN
                RAISE EXCEPTION 'card revision % does not belong to logical card %',
                    NEW.card_revision_id,
                    NEW.card_id;
            END IF;
        END IF;

        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'draw pool members are immutable';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_draw_pool_rarity_weights_immutable
    BEFORE INSERT OR UPDATE OR DELETE ON draw_pool_rarity_weights
    FOR EACH ROW EXECUTE FUNCTION fn_guard_draw_pool_member_change();

CREATE TRIGGER trg_draw_pool_entries_immutable
    BEFORE INSERT OR UPDATE OR DELETE ON draw_pool_entries
    FOR EACH ROW EXECUTE FUNCTION fn_guard_draw_pool_member_change();

CREATE OR REPLACE FUNCTION fn_require_published_draw_pool()
RETURNS TRIGGER AS $$
DECLARE
    selected_pool_id BIGINT;
    parent_published_at TIMESTAMPTZ;
BEGIN
    IF TG_TABLE_NAME = 'collection_system_settings' THEN
        selected_pool_id := NEW.fallback_pool_revision_id;
    ELSE
        selected_pool_id := NEW.active_pool_revision_id;
    END IF;

    IF selected_pool_id IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT published_at
    INTO parent_published_at
    FROM draw_pool_revisions
    WHERE id = selected_pool_id
    FOR SHARE;

    IF NOT FOUND OR parent_published_at IS NULL THEN
        RAISE EXCEPTION 'collection setting requires a published draw pool';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_collection_system_settings_published_pool
    BEFORE INSERT OR UPDATE OF fallback_pool_revision_id ON collection_system_settings
    FOR EACH ROW EXECUTE FUNCTION fn_require_published_draw_pool();

CREATE TRIGGER trg_channel_collection_settings_published_pool
    BEFORE INSERT OR UPDATE OF active_pool_revision_id ON channel_collection_settings
    FOR EACH ROW EXECUTE FUNCTION fn_require_published_draw_pool();

CREATE OR REPLACE FUNCTION fn_require_published_pool_for_draw()
RETURNS TRIGGER AS $$
DECLARE
    parent_published_at TIMESTAMPTZ;
BEGIN
    SELECT published_at
    INTO parent_published_at
    FROM draw_pool_revisions
    WHERE id = NEW.pool_revision_id
    FOR SHARE;

    IF NOT FOUND OR parent_published_at IS NULL THEN
        RAISE EXCEPTION 'viewer card draws require a published draw pool';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_viewer_card_draws_published_pool
    BEFORE INSERT ON viewer_card_draws
    FOR EACH ROW EXECUTE FUNCTION fn_require_published_pool_for_draw();

CREATE OR REPLACE FUNCTION fn_prevent_viewer_card_draw_change()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE'
       AND NOT EXISTS (
           SELECT 1
           FROM channels
           WHERE channel_id = OLD.channel_id
       ) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'viewer card draws are immutable';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_viewer_card_draws_immutable
    BEFORE UPDATE OR DELETE ON viewer_card_draws
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_viewer_card_draw_change();

CREATE POLICY p_channel_collection_settings_tenant ON channel_collection_settings
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));

CREATE POLICY p_viewer_card_draws_tenant ON viewer_card_draws
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));

-- Policies follow the staged RLS rollout and remain inactive for now.
