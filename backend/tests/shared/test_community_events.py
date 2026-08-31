"""Tests for the allowlisted community renderer event catalog."""

import pytest

from shared.community_events import validate_community_event


def test_accepts_known_complete_payload():
    validate_community_event(
        "checkin.recorded",
        1,
        {"total_days": 3, "checkin_date": "2026-08-30"},
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
