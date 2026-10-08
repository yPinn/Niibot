"""discord.py 429 log records are counted for the admin Monitor."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from core.rate_limit_tracker import DiscordRateLimitTracker


def _record(msg: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord("discord.http", logging.WARNING, __file__, 1, msg, args, None)


def test_counts_route_and_global_429s_and_ignores_other_records() -> None:
    client = MagicMock()
    client.is_ws_ratelimited.return_value = False
    tracker = DiscordRateLimitTracker(client)
    tracker.emit(
        _record(
            "We are being rate limited. %s %s responded with 429. Retrying in %.2f seconds.",
            "GET",
            "/x",
            1.0,
        )
    )
    tracker.emit(
        _record("%s %s received a 429 despite having %s remaining requests.", "GET", "/x", 3)
    )
    tracker.emit(_record("Global rate limit has been hit. Retrying in %.2f seconds.", 2.0))
    tracker.emit(_record("Done sleeping for the rate limit. Retrying..."))

    rest, gateway = tracker.snapshots()
    assert rest["name"] == "discord.rest"
    assert rest["rejected"] == 3
    assert rest["last_rejected_at"] is not None
    assert gateway["limited"] is False


def test_gateway_reports_live_ws_throttling() -> None:
    client = MagicMock()
    client.is_ws_ratelimited.return_value = True
    _, gateway = DiscordRateLimitTracker(client).snapshots()
    assert gateway["limited"] is True
