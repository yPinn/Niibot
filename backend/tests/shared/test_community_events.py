"""Tests for the allowlisted community renderer event catalog."""

import pytest

from shared.community_events import validate_community_event


def test_accepts_known_complete_payload():
    validate_community_event(
        "checkin.recorded",
        1,
        {"total_days": 3, "checkin_date": "2026-08-30"},
    )


def test_accepts_checkin_payload_with_a_complete_collection_snapshot():
    validate_community_event(
        "checkin.recorded",
        1,
        {
            "total_days": 3,
            "checkin_date": "2026-08-30",
            "collection": {
                "draw_id": 61,
                "pool_revision_id": 51,
                "algorithm_version": "weighted-rarity-v1",
                "card": {
                    "id": 31,
                    "revision_id": 41,
                    "key": "first-step",
                    "number": "001",
                    "name": "第一步",
                    "artwork": {
                        "portrait_url": None,
                        "square_url": "/images/collections/first-step-square.webp",
                        "backdrop_url": None,
                    },
                },
                "set": {"id": 11, "key": "starter", "name": "起始收藏"},
                "rarity": {
                    "key": "common",
                    "label": "普通",
                    "rank": 10,
                    "effect_intensity": 10,
                },
                "is_new": False,
                "copy_count": 2,
                "progress": {"owned_copies": 4, "unique_cards": 3, "total_cards": 9},
                "owned_cards": [
                    {
                        "card": {
                            "id": 31,
                            "revision_id": 41,
                            "key": "first-step",
                            "number": "001",
                            "name": "第一步",
                            "artwork": {
                                "portrait_url": None,
                                "square_url": "/images/collections/first-step-square.webp",
                                "backdrop_url": None,
                            },
                        },
                        "rarity": {
                            "key": "common",
                            "label": "普通",
                            "rank": 10,
                            "effect_intensity": 10,
                        },
                        "copy_count": 2,
                    },
                    {
                        "card": {
                            "id": 32,
                            "revision_id": 42,
                            "key": "second-step",
                            "number": "002",
                            "name": "第二步",
                            "artwork": {
                                "portrait_url": "/images/collections/second-step.webp",
                                "square_url": None,
                                "backdrop_url": None,
                            },
                        },
                        "rarity": {
                            "key": "common",
                            "label": "普通",
                            "rank": 10,
                            "effect_intensity": 10,
                        },
                        "copy_count": 1,
                    },
                    {
                        "card": {
                            "id": 33,
                            "revision_id": 43,
                            "key": "third-step",
                            "number": "003",
                            "name": "第三步",
                            "artwork": {
                                "portrait_url": None,
                                "square_url": None,
                                "backdrop_url": None,
                            },
                        },
                        "rarity": {
                            "key": "rare",
                            "label": "稀有",
                            "rank": 20,
                            "effect_intensity": 50,
                        },
                        "copy_count": 1,
                    },
                ],
            },
        },
    )


def test_accepts_legacy_collection_snapshot_without_owned_cards():
    validate_community_event(
        "checkin.recorded",
        1,
        {
            "total_days": 3,
            "checkin_date": "2026-08-30",
            "collection": _legacy_collection_snapshot(),
        },
    )


def _legacy_collection_snapshot():
    return {
        "draw_id": 61,
        "pool_revision_id": 51,
        "algorithm_version": "weighted-rarity-v1",
        "card": {
            "id": 31,
            "revision_id": 41,
            "key": "first-step",
            "number": "001",
            "name": "第一步",
            "artwork": {
                "portrait_url": None,
                "square_url": "/images/collections/first-step-square.webp",
                "backdrop_url": None,
            },
        },
        "set": {"id": 11, "key": "starter", "name": "起始收藏"},
        "rarity": {
            "key": "common",
            "label": "普通",
            "rank": 10,
            "effect_intensity": 10,
        },
        "is_new": False,
        "copy_count": 2,
        "progress": {"owned_copies": 4, "unique_cards": 3, "total_cards": 9},
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda snapshot: snapshot["owned_cards"].append(snapshot["owned_cards"][0]),
        lambda snapshot: snapshot["owned_cards"][0].__setitem__("copy_count", 3),
        lambda snapshot: snapshot["owned_cards"].pop(),
        lambda snapshot: snapshot["owned_cards"][0]["card"].__setitem__("id", 99),
        lambda snapshot: snapshot["owned_cards"][0]["card"]["artwork"].__setitem__(
            "portrait_url", "https://untrusted.example/card.webp"
        ),
    ],
)
def test_rejects_inconsistent_complete_inventory(mutate):
    snapshot = _legacy_collection_snapshot()
    snapshot["progress"] = {"owned_copies": 2, "unique_cards": 1, "total_cards": 9}
    snapshot["owned_cards"] = [
        {
            "card": snapshot["card"].copy(),
            "rarity": snapshot["rarity"].copy(),
            "copy_count": 2,
        }
    ]
    snapshot["owned_cards"][0]["card"]["artwork"] = snapshot["card"]["artwork"].copy()
    mutate(snapshot)

    with pytest.raises(ValueError, match="collection"):
        validate_community_event(
            "checkin.recorded",
            1,
            {"total_days": 3, "checkin_date": "2026-08-30", "collection": snapshot},
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda snapshot: snapshot.pop("draw_id"),
        lambda snapshot: snapshot.__setitem__("copy_count", 0),
        lambda snapshot: snapshot["card"].__setitem__("name", ""),
        lambda snapshot: snapshot["rarity"].__setitem__("rank", True),
        lambda snapshot: snapshot["progress"].__setitem__("unique_cards", 10),
        lambda snapshot: snapshot["progress"].__setitem__("unique_cards", 4),
        lambda snapshot: snapshot["progress"].__setitem__("owned_copies", 1),
        lambda snapshot: snapshot.__setitem__("is_new", True),
        lambda snapshot: snapshot["card"]["artwork"].__setitem__(
            "portrait_url", "https://untrusted.example/card.webp"
        ),
    ],
)
def test_rejects_malformed_optional_collection_snapshot(mutate):
    snapshot = {
        "draw_id": 61,
        "pool_revision_id": 51,
        "algorithm_version": "weighted-rarity-v1",
        "card": {
            "id": 31,
            "revision_id": 41,
            "key": "first-step",
            "number": "001",
            "name": "第一步",
            "artwork": {
                "portrait_url": None,
                "square_url": "/images/collections/first-step-square.webp",
                "backdrop_url": None,
            },
        },
        "set": {"id": 11, "key": "starter", "name": "起始收藏"},
        "rarity": {
            "key": "common",
            "label": "普通",
            "rank": 10,
            "effect_intensity": 10,
        },
        "is_new": False,
        "copy_count": 2,
        "progress": {"owned_copies": 4, "unique_cards": 3, "total_cards": 9},
    }
    mutate(snapshot)

    with pytest.raises(ValueError, match="collection"):
        validate_community_event(
            "checkin.recorded",
            1,
            {"total_days": 3, "checkin_date": "2026-08-30", "collection": snapshot},
        )


def test_accepts_complete_tarot_payload():
    validate_community_event(
        "tarot.drawn",
        1,
        {
            "card_id": "0",
            "card_name": "愚者",
            "card_name_en": "The Fool",
            "orientation": "upright",
            "orientation_label": "正位",
            "category": "general",
            "category_label": "綜合",
            "keywords": ["新開始", "冒險", "自由"],
            "meaning": "進入全新階段，無限可能展開。",
            "advice": "保持開放心態。",
            "image_path": "/images/tarot/decks/example/v1/cards/major-00-the-fool.jpg",
            "deck_id": "example",
            "deck_version": 1,
        },
    )


def test_rejects_unknown_schema_version():
    with pytest.raises(ValueError, match="Unknown community event schema"):
        validate_community_event("checkin.recorded", 2, {})


def test_rejects_missing_renderer_field():
    with pytest.raises(ValueError, match="checkin_date"):
        validate_community_event("checkin.recorded", 1, {"total_days": 3})


def test_rejects_incomplete_tarot_payload():
    with pytest.raises(ValueError, match="image_path"):
        validate_community_event("tarot.drawn", 1, {"card_id": "0"})
