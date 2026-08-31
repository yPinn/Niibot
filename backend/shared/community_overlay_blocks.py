"""Registered Live Display blocks and their renderer contracts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

from shared.community_events import CHECKIN_RECORDED
from shared.community_overlay_themes import (
    DEFAULT_OVERLAY_THEME,
    OVERLAY_RENDERER,
    OVERLAY_THEME_SCHEMA_VERSION,
    validate_overlay_theme,
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


def _checkin_preview_payload(now: datetime) -> dict[str, object]:
    return {
        "total_days": 8,
        "checkin_date": now.date().isoformat(),
        "preview": True,
    }


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
        build_preview_payload=_checkin_preview_payload,
    )
}


def get_community_overlay_block(block_type: str) -> CommunityOverlayBlockDefinition:
    try:
        return COMMUNITY_OVERLAY_BLOCKS[block_type]
    except KeyError:
        raise ValueError(f"Unsupported overlay block: {block_type}") from None
