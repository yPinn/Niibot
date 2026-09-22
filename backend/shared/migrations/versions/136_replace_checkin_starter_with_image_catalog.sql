-- Replace the placeholder starter with the first image-backed official catalog.
-- This intentionally resets collection ownership while preserving check-in history.

CREATE TEMP TABLE niibot_retired_collection_sets ON COMMIT DROP AS
SELECT id
FROM collection_sets
WHERE set_key = 'first-path';

CREATE TEMP TABLE niibot_retired_draw_pools ON COMMIT DROP AS
SELECT id
FROM draw_pool_revisions
WHERE pool_key = 'official-starter'
UNION
SELECT DISTINCT entry.pool_revision_id
FROM draw_pool_entries AS entry
JOIN collection_card_revisions AS revision
  ON revision.id = entry.card_revision_id
JOIN collection_cards AS card ON card.id = revision.card_id
WHERE card.set_id IN (SELECT id FROM niibot_retired_collection_sets);

CREATE TEMP TABLE niibot_image_catalog (
    set_key       TEXT NOT NULL,
    card_key      TEXT NOT NULL,
    card_number   SMALLINT NOT NULL,
    display_name  TEXT NOT NULL,
    portrait_url  TEXT NOT NULL
) ON COMMIT DROP;

INSERT INTO niibot_image_catalog
    (set_key, card_key, card_number, display_name, portrait_url)
VALUES
    ('aespa', 'karina-01', 1, 'Karina', '/images/collections/aespa/karina-01-r1.webp'),
    ('aespa', 'karina-02', 2, 'Karina', '/images/collections/aespa/karina-02-r1.webp'),
    ('aespa', 'karina-03', 3, 'Karina', '/images/collections/aespa/karina-03-r1.webp'),
    ('aespa', 'karina-04', 4, 'Karina', '/images/collections/aespa/karina-04-r1.webp'),
    ('aespa', 'karina-05', 5, 'Karina', '/images/collections/aespa/karina-05-r1.webp'),
    ('aespa', 'winter-01', 6, 'Winter', '/images/collections/aespa/winter-01-r1.webp'),
    ('aespa', 'winter-02', 7, 'Winter', '/images/collections/aespa/winter-02-r1.webp'),
    ('aespa', 'winter-03', 8, 'Winter', '/images/collections/aespa/winter-03-r1.webp'),
    ('aespa', 'winter-04', 9, 'Winter', '/images/collections/aespa/winter-04-r1.webp'),
    ('bts', 'jungkook-01', 1, 'Jungkook', '/images/collections/bts/jungkook-01-r1.webp'),
    ('bts', 'jungkook-02', 2, 'Jungkook', '/images/collections/bts/jungkook-02-r1.webp'),
    ('bts', 'jungkook-03', 3, 'Jungkook', '/images/collections/bts/jungkook-03-r1.webp'),
    ('bts', 'v-01', 4, 'V', '/images/collections/bts/v-01-r1.webp'),
    ('bts', 'v-02', 5, 'V', '/images/collections/bts/v-02-r1.webp'),
    ('bts', 'v-03', 6, 'V', '/images/collections/bts/v-03-r1.webp'),
    ('bts', 'v-04', 7, 'V', '/images/collections/bts/v-04-r1.webp'),
    ('bts', 'v-05', 8, 'V', '/images/collections/bts/v-05-r1.webp'),
    ('itzy', 'yuna-01', 1, 'Yuna', '/images/collections/itzy/yuna-01-r1.webp'),
    ('itzy', 'yuna-02', 2, 'Yuna', '/images/collections/itzy/yuna-02-r1.webp'),
    ('itzy', 'yuna-03', 3, 'Yuna', '/images/collections/itzy/yuna-03-r1.webp'),
    ('ive', 'leeseo-01', 1, 'Leeseo', '/images/collections/ive/leeseo-01-r1.webp'),
    ('ive', 'liz-01', 2, 'Liz', '/images/collections/ive/liz-01-r1.webp'),
    ('ive', 'liz-02', 3, 'Liz', '/images/collections/ive/liz-02-r1.webp'),
    ('ive', 'liz-03', 4, 'Liz', '/images/collections/ive/liz-03-r1.webp'),
    ('ive', 'liz-04', 5, 'Liz', '/images/collections/ive/liz-04-r1.webp'),
    ('ive', 'rei-01', 6, 'Rei', '/images/collections/ive/rei-01-r1.webp'),
    ('ive', 'rei-02', 7, 'Rei', '/images/collections/ive/rei-02-r1.webp'),
    ('ive', 'wonyoung-01', 8, 'Wonyoung', '/images/collections/ive/wonyoung-01-r1.webp'),
    ('ive', 'wonyoung-02', 9, 'Wonyoung', '/images/collections/ive/wonyoung-02-r1.webp'),
    ('ive', 'wonyoung-03', 10, 'Wonyoung', '/images/collections/ive/wonyoung-03-r1.webp'),
    ('ive', 'wonyoung-04', 11, 'Wonyoung', '/images/collections/ive/wonyoung-04-r1.webp'),
    ('le-sserafim', 'chaewon-01', 1, 'Chaewon', '/images/collections/le-sserafim/chaewon-01-r1.webp'),
    ('le-sserafim', 'chaewon-02', 2, 'Chaewon', '/images/collections/le-sserafim/chaewon-02-r1.webp'),
    ('le-sserafim', 'chaewon-03', 3, 'Chaewon', '/images/collections/le-sserafim/chaewon-03-r1.webp'),
    ('nmixx', 'haewon-01', 1, 'Haewon', '/images/collections/nmixx/haewon-01-r1.webp'),
    ('nmixx', 'haewon-02', 2, 'Haewon', '/images/collections/nmixx/haewon-02-r1.webp'),
    ('nmixx', 'haewon-03', 3, 'Haewon', '/images/collections/nmixx/haewon-03-r1.webp'),
    ('nmixx', 'haewon-04', 4, 'Haewon', '/images/collections/nmixx/haewon-04-r1.webp'),
    ('nmixx', 'haewon-05', 5, 'Haewon', '/images/collections/nmixx/haewon-05-r1.webp'),
    ('nmixx', 'sullyoon-01', 6, 'Sullyoon', '/images/collections/nmixx/sullyoon-01-r1.webp'),
    ('nmixx', 'sullyoon-02', 7, 'Sullyoon', '/images/collections/nmixx/sullyoon-02-r1.webp'),
    ('nmixx', 'sullyoon-03', 8, 'Sullyoon', '/images/collections/nmixx/sullyoon-03-r1.webp'),
    ('nmixx', 'sullyoon-04', 9, 'Sullyoon', '/images/collections/nmixx/sullyoon-04-r1.webp'),
    ('uc', 'eunha-01', 1, 'Eunha', '/images/collections/uc/eunha-01-r1.webp'),
    ('uc', 'eunha-02', 2, 'Eunha', '/images/collections/uc/eunha-02-r1.webp'),
    ('uc', 'eunha-03', 3, 'Eunha', '/images/collections/uc/eunha-03-r1.webp'),
    ('uc', 'eunha-04', 4, 'Eunha', '/images/collections/uc/eunha-04-r1.webp'),
    ('uc', 'eunha-05', 5, 'Eunha', '/images/collections/uc/eunha-05-r1.webp');

INSERT INTO collection_sets
    (set_key, revision_number, display_name, total_cards)
VALUES
    ('aespa', 1, 'aespa', 9),
    ('bts', 1, 'BTS', 8),
    ('itzy', 1, 'ITZY', 3),
    ('ive', 1, 'IVE', 11),
    ('le-sserafim', 1, 'LE SSERAFIM', 3),
    ('nmixx', 1, 'NMIXX', 9),
    ('uc', 1, 'Eunha', 5);

INSERT INTO collection_cards
    (set_id, card_key, card_number, rarity_revision_id)
SELECT collection_set.id, item.card_key, item.card_number, rarity.id
FROM niibot_image_catalog AS item
JOIN collection_sets AS collection_set
  ON collection_set.set_key = item.set_key
 AND collection_set.revision_number = 1
CROSS JOIN rarity_definition_revisions AS rarity
WHERE rarity.rarity_key = 'common'
  AND rarity.revision_number = 1;

INSERT INTO collection_card_revisions
    (card_id, revision_number, display_name, description, portrait_url)
SELECT card.id, 1, item.display_name, '', item.portrait_url
FROM niibot_image_catalog AS item
JOIN collection_sets AS collection_set
  ON collection_set.set_key = item.set_key
 AND collection_set.revision_number = 1
JOIN collection_cards AS card
  ON card.set_id = collection_set.id
 AND card.card_key = item.card_key;

UPDATE collection_sets
SET published_at = NOW()
WHERE revision_number = 1
  AND set_key IN (SELECT DISTINCT set_key FROM niibot_image_catalog);

CREATE TEMP TABLE niibot_official_pool_definitions (
    pool_key  TEXT NOT NULL,
    set_key   TEXT
) ON COMMIT DROP;

INSERT INTO niibot_official_pool_definitions (pool_key, set_key)
VALUES
    ('official-all', NULL),
    ('official-set-aespa', 'aespa'),
    ('official-set-bts', 'bts'),
    ('official-set-itzy', 'itzy'),
    ('official-set-ive', 'ive'),
    ('official-set-le-sserafim', 'le-sserafim'),
    ('official-set-nmixx', 'nmixx'),
    ('official-set-uc', 'uc');

INSERT INTO draw_pool_revisions
    (pool_key, revision_number, algorithm_version)
SELECT pool_key, 1, 'weighted-rarity-v1'
FROM niibot_official_pool_definitions;

INSERT INTO draw_pool_rarity_weights
    (pool_revision_id, rarity_revision_id, weight)
SELECT pool.id, rarity.id, 100
FROM draw_pool_revisions AS pool
JOIN niibot_official_pool_definitions AS definition
  ON definition.pool_key = pool.pool_key
CROSS JOIN rarity_definition_revisions AS rarity
WHERE pool.revision_number = 1
  AND rarity.rarity_key = 'common'
  AND rarity.revision_number = 1;

INSERT INTO draw_pool_entries
    (pool_revision_id, card_revision_id, card_id, entry_order)
SELECT
    pool.id,
    revision.id,
    card.id,
    ROW_NUMBER() OVER (
        PARTITION BY pool.id
        ORDER BY collection_set.set_key, card.card_number
    )::INT
FROM draw_pool_revisions AS pool
JOIN niibot_official_pool_definitions AS definition
  ON definition.pool_key = pool.pool_key
JOIN collection_sets AS collection_set
  ON definition.set_key IS NULL OR collection_set.set_key = definition.set_key
JOIN collection_cards AS card ON card.set_id = collection_set.id
JOIN collection_card_revisions AS revision
  ON revision.card_id = card.id
 AND revision.revision_number = 1
WHERE pool.revision_number = 1
  AND collection_set.revision_number = 1
  AND collection_set.set_key IN (SELECT DISTINCT set_key FROM niibot_image_catalog);

UPDATE draw_pool_revisions
SET published_at = NOW()
WHERE revision_number = 1
  AND pool_key IN (SELECT pool_key FROM niibot_official_pool_definitions);

UPDATE collection_system_settings
SET fallback_pool_revision_id = (
        SELECT id
        FROM draw_pool_revisions
        WHERE pool_key = 'official-all'
          AND revision_number = 1
          AND published_at IS NOT NULL
    ),
    updated_at = NOW()
WHERE singleton = 1;

DELETE FROM channel_collection_settings;
DELETE FROM community_overlay_events WHERE payload ? 'collection';

ALTER TABLE viewer_card_draws DISABLE TRIGGER trg_viewer_card_draws_immutable;
DELETE FROM viewer_card_draws;
ALTER TABLE viewer_card_draws ENABLE TRIGGER trg_viewer_card_draws_immutable;

ALTER TABLE draw_pool_entries DISABLE TRIGGER trg_draw_pool_entries_immutable;
DELETE FROM draw_pool_entries
WHERE pool_revision_id IN (SELECT id FROM niibot_retired_draw_pools);
ALTER TABLE draw_pool_entries ENABLE TRIGGER trg_draw_pool_entries_immutable;

ALTER TABLE draw_pool_rarity_weights DISABLE TRIGGER trg_draw_pool_rarity_weights_immutable;
DELETE FROM draw_pool_rarity_weights
WHERE pool_revision_id IN (SELECT id FROM niibot_retired_draw_pools);
ALTER TABLE draw_pool_rarity_weights ENABLE TRIGGER trg_draw_pool_rarity_weights_immutable;

ALTER TABLE draw_pool_revisions DISABLE TRIGGER trg_draw_pool_revisions_immutable;
DELETE FROM draw_pool_revisions
WHERE id IN (SELECT id FROM niibot_retired_draw_pools)
   OR pool_key = 'official-starter';
ALTER TABLE draw_pool_revisions ENABLE TRIGGER trg_draw_pool_revisions_immutable;

ALTER TABLE collection_card_revisions DISABLE TRIGGER trg_collection_card_revisions_immutable;
DELETE FROM collection_card_revisions
WHERE card_id IN (
    SELECT id
    FROM collection_cards
    WHERE set_id IN (SELECT id FROM niibot_retired_collection_sets)
);
ALTER TABLE collection_card_revisions ENABLE TRIGGER trg_collection_card_revisions_immutable;

ALTER TABLE collection_cards DISABLE TRIGGER trg_collection_cards_immutable;
DELETE FROM collection_cards
WHERE set_id IN (SELECT id FROM niibot_retired_collection_sets);
ALTER TABLE collection_cards ENABLE TRIGGER trg_collection_cards_immutable;

ALTER TABLE collection_sets DISABLE TRIGGER trg_collection_sets_publish_once;
DELETE FROM collection_sets
WHERE id IN (SELECT id FROM niibot_retired_collection_sets)
   OR set_key = 'first-path';
ALTER TABLE collection_sets ENABLE TRIGGER trg_collection_sets_publish_once;
