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
_MIN_TEXT_CONTRAST = 4.5
_MIN_ACCENT_CONTRAST = 3.0


class CommunityOverlayThemeVersionConflictError(ConflictError):
    code = "COMMUNITY_OVERLAY.THEME_CONFLICT"
    user_message = "樣式草稿已在其他分頁更新，請重新載入"


def _relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(foreground: str, background: str) -> float:
    foreground_luminance = _relative_luminance(foreground)
    background_luminance = _relative_luminance(background)
    light = max(foreground_luminance, background_luminance)
    dark = min(foreground_luminance, background_luminance)
    return (light + 0.05) / (dark + 0.05)


def validate_overlay_theme(value: Mapping[str, object]) -> dict[str, object]:
    """Validate and normalize the complete v1 theme without accepting extensions."""
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

    text_color = str(normalized["text_color"])
    for background_field in ("surface_color", "accent_color"):
        background_color = str(normalized[background_field])
        if _contrast_ratio(text_color, background_color) < _MIN_TEXT_CONTRAST:
            raise ValueError(
                f"text_color must have at least 4.5:1 contrast against {background_field}"
            )
    if (
        _contrast_ratio(str(normalized["accent_color"]), str(normalized["surface_color"]))
        < _MIN_ACCENT_CONTRAST
    ):
        raise ValueError("accent_color must have at least 3:1 contrast against surface_color")

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
