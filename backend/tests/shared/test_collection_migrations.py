"""Static contracts for the immutable daily check-in collection schema."""

import json
from pathlib import Path

_VERSIONS = Path(__file__).parents[2] / "shared" / "migrations" / "versions"
_SCHEMA = _VERSIONS / "112_add_checkin_collections.sql"
_SEED = _VERSIONS / "113_seed_official_checkin_starter_pool.sql"
_CHECKIN_RESET = _VERSIONS / "131_allow_checkin_collection_reset.sql"
_IMAGE_CATALOG = _VERSIONS / "136_replace_checkin_starter_with_image_catalog.sql"
_ARTWORK_CATALOG = Path(__file__).parents[3] / "artwork" / "collections" / "catalog.json"


def test_collection_schema_separates_catalog_pool_and_draw_facts() -> None:
    sql = _SCHEMA.read_text(encoding="utf-8")

    for table in (
        "rarity_definition_revisions",
        "collection_sets",
        "collection_cards",
        "collection_card_revisions",
        "draw_pool_revisions",
        "draw_pool_rarity_weights",
        "draw_pool_entries",
        "collection_system_settings",
        "channel_collection_settings",
        "viewer_card_draws",
    ):
        assert f"CREATE TABLE {table}" in sql

    assert "UNIQUE (channel_id, user_id, id)" in sql
    assert "UNIQUE (checkin_id)" in sql
    assert "FOREIGN KEY (channel_id, user_id, checkin_id)" in sql
    assert "FOREIGN KEY (pool_revision_id, card_revision_id)" in sql
    assert "FOREIGN KEY (pool_revision_id, algorithm_version)" in sql
    assert "UNIQUE (id, algorithm_version)" in sql
    assert "UNIQUE (pool_revision_id, card_id)" in sql
    assert "FOREIGN KEY (card_revision_id, card_id)" in sql
    assert "DEFERRABLE INITIALLY DEFERRED" in sql
    assert "CHECK (octet_length(entropy) = 16)" in sql
    assert "rarity_roll < rarity_weight_total" in sql
    assert "card_roll < card_bucket_size" in sql
    assert "algorithm_version" in sql
    assert "rarity_roll" in sql
    assert "card_roll" in sql


def test_collection_schema_is_tenant_scoped_and_append_only() -> None:
    sql = _SCHEMA.read_text(encoding="utf-8")

    for table in ("channel_collection_settings", "viewer_card_draws"):
        assert f"p_{table}_tenant" in sql
    assert sql.count("fn_tenant_match(channel_id)") >= 4
    assert "ENABLE ROW LEVEL SECURITY" not in sql
    assert "trg_viewer_card_draws_immutable" in sql
    assert "BEFORE UPDATE OR DELETE ON viewer_card_draws" in sql
    assert "trg_collection_card_revisions_immutable" in sql
    assert "trg_draw_pool_revisions_immutable" in sql
    assert "trg_draw_pool_entries_immutable" in sql
    assert "FOR SHARE" in sql
    assert "trg_collection_system_settings_published_pool" in sql
    assert "trg_channel_collection_settings_published_pool" in sql
    assert "trg_viewer_card_draws_published_pool" in sql
    assert "cannot be published without entries" in sql


def test_collection_schema_and_seed_data_are_separate_migrations() -> None:
    schema_sql = _SCHEMA.read_text(encoding="utf-8")
    seed_sql = _SEED.read_text(encoding="utf-8")

    assert "INSERT INTO rarity_definition_revisions" not in schema_sql
    assert "INSERT INTO collection_cards" not in schema_sql
    assert "INSERT INTO rarity_definition_revisions" in seed_sql
    assert "INSERT INTO collection_cards" in seed_sql
    assert "INSERT INTO draw_pool_revisions" in seed_sql
    assert "INSERT INTO collection_system_settings" in seed_sql


def test_official_starter_pool_has_three_nonempty_tiers_and_fixed_weights() -> None:
    sql = _SEED.read_text(encoding="utf-8")
    normalized = " ".join(sql.split()).lower()

    for rarity in ("common", "rare", "legendary"):
        assert f"'{rarity}'" in normalized
    assert "('common', 1, '普通', 10, 20)" in normalized
    assert "('rare', 1, '稀有', 20, 55)" in normalized
    assert "('legendary', 1, '傳說', 30, 100)" in normalized
    assert "'common', 70" in normalized
    assert "'rare', 25" in normalized
    assert "'legendary', 5" in normalized
    assert normalized.count("insert into collection_cards") == 1
    assert "update collection_sets" in normalized
    assert "update draw_pool_revisions" in normalized


def test_official_starter_catalog_uses_original_product_identifiers() -> None:
    sql = _SEED.read_text(encoding="utf-8").lower()

    for original_key in (
        "astral-compass",
        "echo-stone",
        "mist-lantern",
        "moonwell-flask",
        "verdant-gate",
        "first-path-crown",
    ):
        assert original_key in sql
    for protected_term in ("greed island", "hunter x hunter", "pokemon", "yu-gi-oh"):
        assert protected_term not in sql


def test_checkin_reset_keeps_draws_immutable_until_the_parent_is_removed() -> None:
    sql = _CHECKIN_RESET.read_text(encoding="utf-8")

    assert "CREATE OR REPLACE FUNCTION fn_prevent_viewer_card_draw_change()" in sql
    assert "NOT EXISTS" in sql
    assert "FROM viewer_checkins" in sql
    assert "channel_id = OLD.channel_id" in sql
    assert "user_id = OLD.user_id" in sql
    assert "id = OLD.checkin_id" in sql
    assert "DISABLE TRIGGER" not in sql
    assert "DROP TRIGGER" not in sql


def test_image_catalog_replaces_starter_with_every_versioned_artwork() -> None:
    sql = _IMAGE_CATALOG.read_text(encoding="utf-8")
    catalog = json.loads(_ARTWORK_CATALOG.read_text(encoding="utf-8"))

    expected_cards = 0
    for collection in catalog["collections"]:
        assert f"'{collection['key']}'" in sql
        for card in collection["cards"]:
            expected_cards += 1
            assert f"'{card['key']}'" in sql
            assert (
                f"'/images/collections/{collection['key']}/{card['key']}-r{card['revision']}.webp'"
            ) in sql

    normalized = " ".join(sql.split()).lower()
    assert expected_cards == 48
    assert "'official-all'" in normalized
    assert normalized.count("'official-set-") >= 7
    assert "(pool_revision_id, card_revision_id, card_id, entry_order)" in normalized
    assert "delete from viewer_card_draws" in normalized
    assert "delete from channel_collection_settings" in normalized
    assert "delete from community_overlay_events" in normalized
    assert "payload ? 'collection'" in normalized
    assert "set_key = 'first-path'" in normalized
    assert "pool_key = 'official-starter'" in normalized
    assert "delete from collection_sets" in normalized
    assert "delete from draw_pool_revisions" in normalized


def test_image_catalog_reset_preserves_checkin_ledger_and_restores_guards() -> None:
    sql = _IMAGE_CATALOG.read_text(encoding="utf-8")
    normalized = " ".join(sql.split()).lower()

    assert "delete from viewer_checkins" not in normalized
    assert "disable trigger trg_viewer_card_draws_immutable" in normalized
    assert "enable trigger trg_viewer_card_draws_immutable" in normalized
    assert "disable trigger trg_collection_sets_publish_once" in normalized
    assert "enable trigger trg_collection_sets_publish_once" in normalized
    assert "update collection_system_settings" in normalized
    assert "fallback_pool_revision_id" in normalized
