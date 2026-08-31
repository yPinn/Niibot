"""Build renderer-safe Tarot payloads from canonical content and deck catalogs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from shared.tarot_assets import TarotDeckCatalog, get_tarot_card_asset_path
from shared.tarot_reading import TAROT_CATEGORY_LABELS


def build_tarot_overlay_payload(
    *,
    tarot_data: Mapping[str, Any],
    deck_catalog: TarotDeckCatalog,
    card_id: str,
    is_reversed: bool,
    category: str,
    preview: bool = False,
) -> dict[str, object]:
    """Create the complete immutable payload consumed by the OBS renderer."""
    cards = tarot_data.get("cards")
    if not isinstance(cards, Mapping) or card_id not in cards:
        raise ValueError(f"Unknown Tarot card id: {card_id}")
    if category not in TAROT_CATEGORY_LABELS:
        category = "general"

    card = cards[card_id]
    if not isinstance(card, Mapping):
        raise ValueError(f"Invalid Tarot card data: {card_id}")
    orientation = "reversed" if is_reversed else "upright"
    info = card.get(orientation)
    if not isinstance(info, Mapping):
        raise ValueError(f"Missing Tarot {orientation} data: {card_id}")
    meanings = info.get("meanings")
    if not isinstance(meanings, Mapping):
        raise ValueError(f"Missing Tarot meanings: {card_id}")

    keywords = info.get("keywords")
    if not isinstance(keywords, list) or not all(isinstance(item, str) for item in keywords):
        raise ValueError(f"Invalid Tarot keywords: {card_id}")

    deck = deck_catalog.active_deck
    payload: dict[str, object] = {
        "card_id": card_id,
        "card_name": str(card["name"]),
        "card_name_en": str(card["name_en"]),
        "orientation": orientation,
        "orientation_label": "逆位" if is_reversed else "正位",
        "category": category,
        "category_label": TAROT_CATEGORY_LABELS[category],
        "keywords": keywords,
        "meaning": str(meanings.get(category, meanings["general"])),
        "advice": str(info.get("advice", "靜心思考這張牌對你今天的意義。")),
        "image_path": get_tarot_card_asset_path(deck_catalog, card_id),
        "deck_id": deck.deck_id,
        "deck_version": deck.version,
    }
    if preview:
        payload["preview"] = True
    return payload
