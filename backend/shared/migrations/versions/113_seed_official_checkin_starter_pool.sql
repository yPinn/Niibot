-- Provider-owned original starter catalog and the first published fallback pool.
-- Artwork is intentionally nullable in this core slice; the renderer supplies
-- deterministic original sigils until versioned same-origin art is published.

INSERT INTO rarity_definition_revisions
    (rarity_key, revision_number, display_name, sort_rank, effect_intensity)
VALUES
    ('common', 1, '普通', 10, 20),
    ('rare', 1, '稀有', 20, 55),
    ('legendary', 1, '傳說', 30, 100);

INSERT INTO collection_sets
    (set_key, revision_number, display_name, total_cards)
VALUES
    ('first-path', 1, '初途秘典', 9);

INSERT INTO collection_cards (set_id, card_key, card_number, rarity_revision_id)
SELECT collection_set.id, card.card_key, card.card_number, rarity.id
FROM collection_sets AS collection_set
CROSS JOIN (
    VALUES
        ('astral-compass', 1, 'common'),
        ('echo-stone', 2, 'common'),
        ('mist-lantern', 3, 'common'),
        ('threaded-key', 4, 'common'),
        ('rain-cipher', 5, 'common'),
        ('moonwell-flask', 6, 'rare'),
        ('clockwork-moth', 7, 'rare'),
        ('verdant-gate', 8, 'rare'),
        ('first-path-crown', 9, 'legendary')
) AS card(card_key, card_number, rarity_key)
JOIN rarity_definition_revisions AS rarity
  ON rarity.rarity_key = card.rarity_key
 AND rarity.revision_number = 1
WHERE collection_set.set_key = 'first-path'
  AND collection_set.revision_number = 1;

INSERT INTO collection_card_revisions
    (card_id, revision_number, display_name, description)
SELECT card.id, 1, copy.display_name, copy.description
FROM collection_cards AS card
JOIN collection_sets AS collection_set
  ON collection_set.id = card.set_id
JOIN (
    VALUES
        ('astral-compass', '星羅羅盤', '會朝向持有者此刻最珍惜的方向。'),
        ('echo-stone', '回聲礦石', '封存一句真心話，直到月光喚醒它。'),
        ('mist-lantern', '霧行燈', '在迷霧中照出下一個安全落腳處。'),
        ('threaded-key', '結線鑰匙', '能開啟一扇由約定維繫的門。'),
        ('rain-cipher', '雨之密文', '雨滴落下時才會顯現的旅行筆記。'),
        ('moonwell-flask', '月泉瓶', '盛裝一夜月色，飲下後可看見隱藏道路。'),
        ('clockwork-moth', '刻輪夜蛾', '牠振翅一次，周圍的鐘便慢下一拍。'),
        ('verdant-gate', '翠境之門', '種在土裡，翌日會長成通往遠方的拱門。'),
        ('first-path-crown', '初途王冠', '只在持有者選擇從未走過的道路時發光。')
) AS copy(card_key, display_name, description)
  ON copy.card_key = card.card_key
WHERE collection_set.set_key = 'first-path'
  AND collection_set.revision_number = 1;

UPDATE collection_sets
SET published_at = NOW()
WHERE set_key = 'first-path'
  AND revision_number = 1;

INSERT INTO draw_pool_revisions
    (pool_key, revision_number, algorithm_version)
VALUES
    ('official-starter', 1, 'weighted-rarity-v1');

WITH weights(rarity_key, weight) AS (
    VALUES ('common', 70), ('rare', 25), ('legendary', 5)
)
INSERT INTO draw_pool_rarity_weights (pool_revision_id, rarity_revision_id, weight)
SELECT pool.id, rarity.id, weights.weight
FROM draw_pool_revisions AS pool
CROSS JOIN weights
JOIN rarity_definition_revisions AS rarity
  ON rarity.rarity_key = weights.rarity_key
 AND rarity.revision_number = 1
WHERE pool.pool_key = 'official-starter'
  AND pool.revision_number = 1;

INSERT INTO draw_pool_entries (pool_revision_id, card_revision_id, entry_order)
SELECT pool.id, revision.id, card.card_number
FROM draw_pool_revisions AS pool
CROSS JOIN collection_sets AS collection_set
JOIN collection_cards AS card
  ON card.set_id = collection_set.id
JOIN collection_card_revisions AS revision
  ON revision.card_id = card.id
 AND revision.revision_number = 1
WHERE pool.pool_key = 'official-starter'
  AND pool.revision_number = 1
  AND collection_set.set_key = 'first-path'
  AND collection_set.revision_number = 1;

UPDATE draw_pool_revisions
SET published_at = NOW()
WHERE pool_key = 'official-starter'
  AND revision_number = 1;

INSERT INTO collection_system_settings (singleton, fallback_pool_revision_id)
SELECT 1, id
FROM draw_pool_revisions
WHERE pool_key = 'official-starter'
  AND revision_number = 1
  AND published_at IS NOT NULL;
