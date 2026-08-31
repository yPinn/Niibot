"""Tests for versioned, locally hosted Tarot deck assets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.tarot_assets import (
    get_tarot_card_asset_path,
    get_tarot_card_asset_url,
    parse_tarot_deck_catalog,
)

VALID_CATALOG = {
    "schema_version": 1,
    "active_deck": {"id": "rider-waite-smith-pkt", "version": 1},
    "decks": [
        {
            "id": "rider-waite-smith-pkt",
            "version": 1,
            "display_name": "Rider-Waite-Smith — Pictorial Key to the Tarot",
            "format": "jpg",
            "source_url": "https://sacred-texts.com/tarot/pkt/",
            "download_mirror_url": "https://github.com/sixseeds/tarot-api/tree/main/cards",
            "cards": {
                "0": "major-00-the-fool",
                "1": "major-01-the-magician",
            },
        }
    ],
}


def test_builds_versioned_same_origin_asset_path() -> None:
    catalog = parse_tarot_deck_catalog(VALID_CATALOG, expected_card_ids={"0", "1"})

    assert get_tarot_card_asset_path(catalog, "0") == (
        "/images/tarot/decks/rider-waite-smith-pkt/v1/cards/major-00-the-fool.jpg"
    )


def test_builds_absolute_asset_url_for_discord() -> None:
    catalog = parse_tarot_deck_catalog(VALID_CATALOG, expected_card_ids={"0", "1"})

    assert get_tarot_card_asset_url(catalog, "1", "https://niibot.tv/") == (
        "https://niibot.tv/images/tarot/decks/rider-waite-smith-pkt/v1/cards/"
        "major-01-the-magician.jpg"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "../unsafe"),
        ("format", "svg"),
        ("cards", {"0": "../../escape", "1": "major-01-the-magician"}),
    ],
)
def test_rejects_unsafe_or_unsupported_asset_metadata(field: str, value: object) -> None:
    invalid = json.loads(json.dumps(VALID_CATALOG))
    invalid["decks"][0][field] = value

    with pytest.raises(ValueError):
        parse_tarot_deck_catalog(invalid, expected_card_ids={"0", "1"})


def test_rejects_incomplete_card_mapping() -> None:
    invalid = json.loads(json.dumps(VALID_CATALOG))
    invalid["decks"][0]["cards"].pop("1")

    with pytest.raises(ValueError, match="card ids"):
        parse_tarot_deck_catalog(invalid, expected_card_ids={"0", "1"})


def test_repository_catalog_maps_all_78_cards_to_unique_structured_names() -> None:
    data_dir = Path(__file__).resolve().parents[2] / "data"
    tarot_data = json.loads((data_dir / "tarot.json").read_text(encoding="utf-8"))
    deck_data = json.loads((data_dir / "tarot_decks.json").read_text(encoding="utf-8"))

    catalog = parse_tarot_deck_catalog(deck_data, expected_card_ids=set(tarot_data["cards"]))
    active_deck = catalog.active_deck

    assert len(active_deck.cards) == 78
    assert len(set(active_deck.cards.values())) == 78
    assert active_deck.cards["0"] == "major-00-the-fool"
    assert active_deck.cards["21"] == "major-21-the-world"
    assert active_deck.cards["w01"] == "wands-01-ace-of-wands"
    assert active_deck.cards["p14"] == "pentacles-14-king-of-pentacles"
    assert active_deck.download_mirror_url == (
        "https://github.com/sixseeds/tarot-api/tree/main/cards"
    )
    assert all("image_url" not in card for card in tarot_data["cards"].values())
