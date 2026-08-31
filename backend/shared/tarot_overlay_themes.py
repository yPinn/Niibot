"""Theme contract for the Tarot Live Display renderer."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from shared.community_overlay_themes import DEFAULT_OVERLAY_THEME, validate_overlay_theme

TAROT_OVERLAY_THEME_SCHEMA_VERSION: Final = 1
TAROT_OVERLAY_RENDERER: Final = "tarot-card"

# Tarot needs a longer hold after its reveal, while the tighter radius follows the physical card.
DEFAULT_TAROT_OVERLAY_THEME: Final[dict[str, object]] = {
    **DEFAULT_OVERLAY_THEME,
    "radius_px": 16,
    "display_ms": 5_000,
}


def validate_tarot_overlay_theme(value: Mapping[str, object]) -> dict[str, object]:
    return validate_overlay_theme(value)
