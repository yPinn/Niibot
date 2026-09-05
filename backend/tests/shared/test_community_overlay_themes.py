"""Contracts for the allowlisted community overlay theme schema."""

from __future__ import annotations

import pytest

from shared.community_overlay_themes import DEFAULT_OVERLAY_THEME, validate_overlay_theme
from shared.tarot_overlay_themes import DEFAULT_TAROT_OVERLAY_THEME


def test_default_theme_is_a_valid_complete_schema() -> None:
    assert validate_overlay_theme(DEFAULT_OVERLAY_THEME) == DEFAULT_OVERLAY_THEME
    assert DEFAULT_OVERLAY_THEME["placement"] == "bottom-left"
    assert DEFAULT_OVERLAY_THEME["display_ms"] == 4_000
    assert set(DEFAULT_OVERLAY_THEME) == {
        "surface_color",
        "accent_color",
        "text_color",
        "placement",
        "radius_px",
        "display_ms",
        "motion",
    }


def test_tarot_default_keeps_the_card_visible_after_its_reveal() -> None:
    assert validate_overlay_theme(DEFAULT_TAROT_OVERLAY_THEME) == DEFAULT_TAROT_OVERLAY_THEME
    assert DEFAULT_TAROT_OVERLAY_THEME == {
        **DEFAULT_OVERLAY_THEME,
        "radius_px": 16,
        "display_ms": 5_000,
    }


def test_theme_colors_are_normalized_without_accepting_extra_fields() -> None:
    theme = {
        **DEFAULT_OVERLAY_THEME,
        "surface_color": "#fff7cf",
        "accent_color": "#ef4d88",
    }

    assert validate_overlay_theme(theme) == {
        **theme,
        "surface_color": "#FFF7CF",
        "accent_color": "#EF4D88",
    }

    with pytest.raises(ValueError, match="Unsupported theme fields"):
        validate_overlay_theme({**theme, "custom_css": "body { display: none }"})


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("surface_color", "red", "6-digit hex"),
        ("accent_color", "#12345678", "6-digit hex"),
        ("placement", "center", "placement"),
        ("motion", "extreme", "motion"),
        ("radius_px", -1, "radius_px"),
        ("radius_px", 41, "radius_px"),
        ("display_ms", 1_999, "display_ms"),
        ("display_ms", 15_001, "display_ms"),
        ("display_ms", True, "display_ms"),
    ],
)
def test_theme_rejects_invalid_or_out_of_range_values(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_overlay_theme({**DEFAULT_OVERLAY_THEME, field: value})


def test_theme_rejects_missing_fields() -> None:
    theme = dict(DEFAULT_OVERLAY_THEME)
    theme.pop("motion")

    with pytest.raises(ValueError, match="Missing theme fields"):
        validate_overlay_theme(theme)


def test_theme_accepts_low_contrast_colors_as_a_deliberate_stylistic_choice() -> None:
    """This overlay decorates the streamer's own scene; contrast is advisory only,
    surfaced client-side, and must never block a broadcaster's color choice here."""
    # Identical colors give a 1:1 contrast ratio everywhere — the strictest possible
    # case, and one the old rule rejected on all three pairs simultaneously.
    theme = {
        **DEFAULT_OVERLAY_THEME,
        "surface_color": "#241B34",
        "accent_color": "#241B34",
        "text_color": "#241B34",
    }

    assert validate_overlay_theme(theme) == theme
