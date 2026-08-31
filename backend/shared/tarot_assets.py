"""Validated asset catalog for versioned, locally hosted Tarot decks."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

TAROT_ASSET_CATALOG_SCHEMA_VERSION: Final = 1

_SAFE_SEGMENT = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SUPPORTED_FORMATS = frozenset({"avif", "jpeg", "jpg", "png", "webp"})


@dataclass(frozen=True, slots=True)
class TarotDeckDefinition:
    deck_id: str
    version: int
    display_name: str
    image_format: str
    source_url: str
    download_mirror_url: str
    cards: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class TarotDeckCatalog:
    schema_version: int
    active_deck: TarotDeckDefinition
    decks: tuple[TarotDeckDefinition, ...]


def _require_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _require_safe_segment(value: object, field: str) -> str:
    if not isinstance(value, str) or _SAFE_SEGMENT.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase kebab-case segment")
    return value


def _require_positive_int(value: object, field: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _require_http_url(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field} must be an absolute HTTP URL")
    return value


def _parse_deck(value: object, expected_card_ids: frozenset[str]) -> TarotDeckDefinition:
    deck = _require_mapping(value, "deck")
    deck_id = _require_safe_segment(deck.get("id"), "deck.id")
    version = _require_positive_int(deck.get("version"), "deck.version")

    display_name = deck.get("display_name")
    if not isinstance(display_name, str) or not display_name.strip():
        raise ValueError("deck.display_name must be a non-empty string")

    image_format = deck.get("format")
    if not isinstance(image_format, str) or image_format not in _SUPPORTED_FORMATS:
        raise ValueError("deck.format is unsupported")

    source_url = _require_http_url(deck.get("source_url"), "deck.source_url")
    download_mirror_url = _require_http_url(
        deck.get("download_mirror_url"),
        "deck.download_mirror_url",
    )

    raw_cards = _require_mapping(deck.get("cards"), "deck.cards")
    cards: dict[str, str] = {}
    for card_id, asset_key in raw_cards.items():
        if not isinstance(card_id, str):
            raise ValueError("deck card ids must be strings")
        cards[card_id] = _require_safe_segment(asset_key, f"deck.cards.{card_id}")

    if frozenset(cards) != expected_card_ids:
        raise ValueError("deck card ids must exactly match the Tarot card catalog")
    if len(set(cards.values())) != len(cards):
        raise ValueError("deck asset keys must be unique")

    return TarotDeckDefinition(
        deck_id=deck_id,
        version=version,
        display_name=display_name.strip(),
        image_format=image_format,
        source_url=source_url,
        download_mirror_url=download_mirror_url,
        cards=cards,
    )


def parse_tarot_deck_catalog(
    value: object,
    *,
    expected_card_ids: Iterable[str],
) -> TarotDeckCatalog:
    """Validate a complete deck catalog against the canonical Tarot card ids."""
    root = _require_mapping(value, "catalog")
    schema_version = root.get("schema_version")
    if schema_version != TAROT_ASSET_CATALOG_SCHEMA_VERSION:
        raise ValueError("Unsupported Tarot asset catalog schema version")

    expected_ids = frozenset(expected_card_ids)
    if not expected_ids:
        raise ValueError("expected_card_ids must not be empty")

    raw_decks = root.get("decks")
    if not isinstance(raw_decks, list) or not raw_decks:
        raise ValueError("catalog.decks must be a non-empty list")
    decks = tuple(_parse_deck(deck, expected_ids) for deck in raw_decks)

    deck_keys = [(deck.deck_id, deck.version) for deck in decks]
    if len(set(deck_keys)) != len(deck_keys):
        raise ValueError("deck id and version pairs must be unique")

    active = _require_mapping(root.get("active_deck"), "catalog.active_deck")
    active_key = (
        _require_safe_segment(active.get("id"), "active_deck.id"),
        _require_positive_int(active.get("version"), "active_deck.version"),
    )
    active_deck = next((deck for deck in decks if (deck.deck_id, deck.version) == active_key), None)
    if active_deck is None:
        raise ValueError("active_deck does not reference a registered deck version")

    return TarotDeckCatalog(
        schema_version=TAROT_ASSET_CATALOG_SCHEMA_VERSION,
        active_deck=active_deck,
        decks=decks,
    )


def load_tarot_deck_catalog(
    path: Path,
    *,
    expected_card_ids: Iterable[str],
) -> TarotDeckCatalog:
    value = json.loads(path.read_text(encoding="utf-8"))
    return parse_tarot_deck_catalog(value, expected_card_ids=expected_card_ids)


def get_tarot_card_asset_path(catalog: TarotDeckCatalog, card_id: str) -> str:
    """Return the immutable same-origin public path for one card image."""
    deck = catalog.active_deck
    try:
        asset_key = deck.cards[card_id]
    except KeyError:
        raise ValueError(f"Unknown Tarot card id: {card_id}") from None
    return (
        f"/images/tarot/decks/{deck.deck_id}/v{deck.version}/cards/{asset_key}.{deck.image_format}"
    )


def get_tarot_card_asset_url(
    catalog: TarotDeckCatalog,
    card_id: str,
    frontend_url: str,
) -> str:
    """Return the absolute public URL required by Discord embeds."""
    parsed_frontend = urlsplit(frontend_url)
    if (
        parsed_frontend.scheme not in {"http", "https"}
        or not parsed_frontend.netloc
        or parsed_frontend.query
        or parsed_frontend.fragment
    ):
        raise ValueError("frontend_url must be an absolute HTTP origin or base URL")
    return f"{frontend_url.rstrip('/')}{get_tarot_card_asset_path(catalog, card_id)}"
