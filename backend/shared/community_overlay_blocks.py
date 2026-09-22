"""Registered Live Display blocks and their renderer contracts."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

from shared.community_events import CHECKIN_RECORDED, TAROT_DRAWN
from shared.community_overlay_themes import (
    DEFAULT_OVERLAY_THEME,
    OVERLAY_RENDERER,
    OVERLAY_THEME_SCHEMA_VERSION,
    validate_overlay_theme,
)
from shared.config_base import DATA_DIR
from shared.tarot_assets import load_tarot_deck_catalog
from shared.tarot_overlay import build_tarot_overlay_payload
from shared.tarot_overlay_themes import (
    DEFAULT_TAROT_OVERLAY_THEME,
    TAROT_OVERLAY_RENDERER,
    TAROT_OVERLAY_THEME_SCHEMA_VERSION,
    validate_tarot_overlay_theme,
)


@dataclass(frozen=True, slots=True)
class CommunityOverlayBlockDefinition:
    block_type: str
    renderer: str
    schema_version: int
    default_theme: Mapping[str, object]
    validate_theme: Callable[[Mapping[str, object]], dict[str, object]]
    preview_event_type: str
    preview_event_schema_version: int
    preview_actor_display_name: str
    build_preview_payload: Callable[[datetime], dict[str, object]]


def build_checkin_preview_payload(now: datetime, *, total_days: int = 8) -> dict[str, object]:
    """Build a synthetic binder event without touching the check-in/draw ledger."""
    copy_count = 1 if total_days == 1 else 2
    return {
        "total_days": total_days,
        "checkin_date": now.date().isoformat(),
        "preview": True,
        "collection": {
            "draw_id": 1,
            "pool_revision_id": 1,
            "algorithm_version": "weighted-rarity-v1",
            "card": {
                "id": 1,
                "revision_id": 1,
                "key": "karina-01",
                "number": "001",
                "name": "Karina",
                "artwork": {
                    "portrait_url": "/images/collections/aespa/karina-01-r1.webp",
                    "square_url": None,
                    "backdrop_url": None,
                },
            },
            "set": {"id": 1, "key": "aespa", "name": "aespa"},
            "rarity": {
                "key": "common",
                "label": "普通",
                "rank": 10,
                "effect_intensity": 20,
            },
            "is_new": total_days == 1,
            "copy_count": copy_count,
            "progress": {
                "owned_copies": total_days,
                "unique_cards": min(total_days - copy_count + 1, 48),
                "total_cards": 48,
            },
        },
    }


_TAROT_DATA = json.loads((DATA_DIR / "tarot.json").read_text(encoding="utf-8"))
_TAROT_DECKS = load_tarot_deck_catalog(
    DATA_DIR / "tarot_decks.json",
    expected_card_ids=set(_TAROT_DATA["cards"]),
)


def _tarot_preview_payload(now: datetime) -> dict[str, object]:
    del now
    return build_tarot_overlay_payload(
        tarot_data=_TAROT_DATA,
        deck_catalog=_TAROT_DECKS,
        card_id="0",
        is_reversed=False,
        category="general",
        preview=True,
    )


COMMUNITY_OVERLAY_BLOCKS = {
    "checkin": CommunityOverlayBlockDefinition(
        block_type="checkin",
        renderer=OVERLAY_RENDERER,
        schema_version=OVERLAY_THEME_SCHEMA_VERSION,
        default_theme=DEFAULT_OVERLAY_THEME,
        validate_theme=validate_overlay_theme,
        preview_event_type=CHECKIN_RECORDED.event_type,
        preview_event_schema_version=CHECKIN_RECORDED.schema_version,
        preview_actor_display_name="測試觀眾",
        build_preview_payload=build_checkin_preview_payload,
    ),
    "tarot": CommunityOverlayBlockDefinition(
        block_type="tarot",
        renderer=TAROT_OVERLAY_RENDERER,
        schema_version=TAROT_OVERLAY_THEME_SCHEMA_VERSION,
        default_theme=DEFAULT_TAROT_OVERLAY_THEME,
        validate_theme=validate_tarot_overlay_theme,
        preview_event_type=TAROT_DRAWN.event_type,
        preview_event_schema_version=TAROT_DRAWN.schema_version,
        preview_actor_display_name="測試觀眾",
        build_preview_payload=_tarot_preview_payload,
    ),
}


def get_community_overlay_block(block_type: str) -> CommunityOverlayBlockDefinition:
    try:
        return COMMUNITY_OVERLAY_BLOCKS[block_type]
    except KeyError:
        raise ValueError(f"Unsupported overlay block: {block_type}") from None
