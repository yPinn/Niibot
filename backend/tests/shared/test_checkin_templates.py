"""Tests for the allowlisted daily check-in reply renderer."""

from __future__ import annotations

from datetime import date

import pytest

from shared.checkin_templates import render_checkin_template


def test_renders_only_supported_checkin_variables() -> None:
    rendered = render_checkin_template(
        "$(@user) / $(user) / $(count) / $(streak) / $(date) / $(today_order)",
        username="alice",
        display_name="Alice",
        total_days=12,
        current_streak=4,
        today_order=7,
        checkin_date=date(2026, 8, 31),
    )

    assert rendered == "@Alice / Alice / 12 / 4 / 2026-08-31 / 7"


def test_falls_back_to_login_when_display_name_is_missing() -> None:
    rendered = render_checkin_template(
        "$(@user) $(count)",
        username="alice",
        display_name=None,
        total_days=1,
        checkin_date=date(2026, 8, 31),
    )

    assert rendered == "@alice 1"


def test_rejects_unknown_variables() -> None:
    with pytest.raises(ValueError, match="Unsupported check-in template variable"):
        render_checkin_template(
            "$(user) $(random 1,10)",
            username="alice",
            display_name="Alice",
            total_days=1,
            checkin_date=date(2026, 8, 31),
        )


def test_rejects_output_over_twitch_message_limit() -> None:
    with pytest.raises(ValueError, match="500 characters"):
        render_checkin_template(
            "x" * 500 + "$(count)",
            username="alice",
            display_name="Alice",
            total_days=1,
            checkin_date=date(2026, 8, 31),
        )
