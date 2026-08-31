"""Tarot renderer payload contracts."""

from __future__ import annotations

import json
from pathlib import Path

from shared.tarot_assets import load_tarot_deck_catalog
from shared.tarot_overlay import build_tarot_overlay_payload


def _resources():
    data_dir = Path(__file__).resolve().parents[2] / "data"
    tarot_data = json.loads((data_dir / "tarot.json").read_text(encoding="utf-8"))
    decks = load_tarot_deck_catalog(
        data_dir / "tarot_decks.json",
        expected_card_ids=set(tarot_data["cards"]),
    )
    return tarot_data, decks


def test_builds_complete_reversed_payload_with_pinned_deck_version() -> None:
    tarot_data, decks = _resources()

    payload = build_tarot_overlay_payload(
        tarot_data=tarot_data,
        deck_catalog=decks,
        card_id="p14",
        is_reversed=True,
        category="love",
    )

    assert payload["card_name"] == "錢幣國王"
    assert payload["orientation"] == "reversed"
    assert payload["orientation_label"] == "逆位"
    assert payload["category"] == "love"
    assert payload["category_label"] == "感情"
    assert payload["deck_id"] == "rider-waite-smith-pkt"
    assert payload["deck_version"] == 1
    assert payload["image_path"].endswith("/pentacles-14-king-of-pentacles.jpg")
    assert payload["keywords"]
    assert payload["meaning"]
    assert payload["advice"]


def test_unknown_category_falls_back_to_general() -> None:
    tarot_data, decks = _resources()

    payload = build_tarot_overlay_payload(
        tarot_data=tarot_data,
        deck_catalog=decks,
        card_id="0",
        is_reversed=False,
        category="unknown",
    )

    assert payload["category"] == "general"
    assert payload["category_label"] == "綜合"


def test_every_card_orientation_has_a_distinct_reading_for_each_topic() -> None:
    tarot_data, _ = _resources()

    assert len(tarot_data["cards"]) == 78
    for card_id, card in tarot_data["cards"].items():
        for orientation in ("upright", "reversed"):
            meanings = card[orientation]["meanings"]
            assert set(meanings) >= {"general", "love", "career", "finance"}, (
                f"{card_id} {orientation} is missing a topic reading"
            )
            assert all(
                meanings[topic].strip() for topic in ("general", "love", "career", "finance")
            )
