"""Allowlisted theme contract for the shared community overlay renderer."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

from shared.errors import ConflictError

OVERLAY_THEME_SCHEMA_VERSION: Final = 1
OVERLAY_RENDERER: Final = "checkin-card"

DEFAULT_OVERLAY_THEME: Final[dict[str, object]] = {
    "surface_color": "#FFF7CF",
    "accent_color": "#EF4D88",
    "text_color": "#241B34",
    "placement": "bottom-left",
    "radius_px": 24,
    "display_ms": 4_000,
    "motion": "standard",
}

_THEME_FIELDS = frozenset(DEFAULT_OVERLAY_THEME)
_COLOR_FIELDS = ("surface_color", "accent_color", "text_color")
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_PLACEMENTS = frozenset({"top-left", "top-right", "bottom-left", "bottom-right"})
_MOTIONS = frozenset({"standard", "subtle", "none"})


class CommunityOverlayThemeVersionConflictError(ConflictError):
    code = "COMMUNITY_OVERLAY.THEME_CONFLICT"
    user_message = "樣式草稿已在其他分頁更新，請重新載入"


def validate_overlay_theme(value: Mapping[str, object]) -> dict[str, object]:
    """Validate and normalize the complete v1 theme without accepting extensions.

    Color contrast is intentionally not enforced here: this theme decorates a
    streamer's own OBS scene, not an interface others are required to use, so
    the dashboard only *suggests* accessible contrast (see ThemeEditor.tsx)
    rather than blocking a deliberate stylistic choice.
    """
    keys = frozenset(value)
    missing = _THEME_FIELDS - keys
    if missing:
        raise ValueError(f"Missing theme fields: {', '.join(sorted(missing))}")
    extra = keys - _THEME_FIELDS
    if extra:
        raise ValueError(f"Unsupported theme fields: {', '.join(sorted(extra))}")

    normalized = dict(value)
    for field in _COLOR_FIELDS:
        color = value[field]
        if not isinstance(color, str) or _HEX_COLOR.fullmatch(color) is None:
            raise ValueError(f"{field} must be a 6-digit hex color")
        normalized[field] = color.upper()

    placement = value["placement"]
    if not isinstance(placement, str) or placement not in _PLACEMENTS:
        raise ValueError("placement must be one of the supported corners")

    motion = value["motion"]
    if not isinstance(motion, str) or motion not in _MOTIONS:
        raise ValueError("motion must be standard, subtle, or none")

    radius = value["radius_px"]
    if type(radius) is not int or not 0 <= radius <= 40:
        raise ValueError("radius_px must be an integer between 0 and 40")

    display_ms = value["display_ms"]
    if type(display_ms) is not int or not 2_000 <= display_ms <= 15_000:
        raise ValueError("display_ms must be an integer between 2000 and 15000")

    return normalized
