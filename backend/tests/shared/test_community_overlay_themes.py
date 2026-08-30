"""Contracts for the allowlisted community overlay theme schema."""

from __future__ import annotations

import pytest

from shared.community_overlay_themes import DEFAULT_OVERLAY_THEME, validate_overlay_theme


def test_default_theme_is_a_valid_complete_schema() -> None:
    assert validate_overlay_theme(DEFAULT_OVERLAY_THEME) == DEFAULT_OVERLAY_THEME
    assert set(DEFAULT_OVERLAY_THEME) == {
        "surface_color",
        "accent_color",
        "text_color",
        "placement",
        "radius_px",
        "display_ms",
        "motion",
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


@pytest.mark.parametrize("field", ["surface_color", "accent_color"])
def test_theme_rejects_text_colors_below_accessible_contrast(field: str) -> None:
    with pytest.raises(ValueError, match=rf"4\.5:1 contrast against {field}"):
        validate_overlay_theme({**DEFAULT_OVERLAY_THEME, field: "#241B34"})


def test_theme_rejects_accent_without_visual_separation_from_surface() -> None:
    with pytest.raises(ValueError, match=r"3:1 contrast against surface_color"):
        validate_overlay_theme(
            {
                **DEFAULT_OVERLAY_THEME,
                "surface_color": "#FFFFFF",
                "accent_color": "#FFFFFF",
                "text_color": "#000000",
            }
        )
