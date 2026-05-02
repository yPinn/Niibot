"""Unit tests for _parse_twitch_duration in core._session_mixin."""

from datetime import timedelta

import pytest

from core._session_mixin import _parse_twitch_duration


@pytest.mark.parametrize(
    "s, expected",
    [
        ("3h21m15s", timedelta(hours=3, minutes=21, seconds=15)),
        ("1h0m0s", timedelta(hours=1)),
        ("45m30s", timedelta(minutes=45, seconds=30)),
        ("30s", timedelta(seconds=30)),
        ("2h", timedelta(hours=2)),
        ("10m", timedelta(minutes=10)),
        ("0h0m0s", timedelta()),
        ("", timedelta()),  # empty → zero (safe fallback)
    ],
)
def test_parse_twitch_duration(s: str, expected: timedelta) -> None:
    assert _parse_twitch_duration(s) == expected
