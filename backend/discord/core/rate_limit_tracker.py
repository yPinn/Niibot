"""Count discord.py's REST rate-limit hits for the admin Monitor.

discord.py retries 429s itself and only reports them through the
``discord.http`` logger, so a handler on that logger is the one place they can
be counted without patching the library. Gateway throttling has a public
check (``Client.is_ws_ratelimited``) and is read live instead.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from shared import rate_limits
from shared.rate_limits import RateLimitSnapshot

if TYPE_CHECKING:
    from discord import Client

# Message templates discord.py 2.x logs on a 429 (matched on the unformatted
# template, so arguments never matter).
_PER_ROUTE_MARKERS = ("responded with 429", "received a 429")
_GLOBAL_MARKER = "Global rate limit has been hit"


class DiscordRateLimitTracker(logging.Handler):
    def __init__(self, client: Client) -> None:
        super().__init__(level=logging.DEBUG)
        self._client = client
        self.route_hits = 0
        self.global_hits = 0
        self.last_hit_at: float | None = None

    def emit(self, record: logging.LogRecord) -> None:
        template = str(record.msg)
        if template.startswith(_GLOBAL_MARKER):
            self.global_hits += 1
        elif any(marker in template for marker in _PER_ROUTE_MARKERS):
            self.route_hits += 1
        else:
            return
        self.last_hit_at = time.time()

    def snapshots(self) -> list[RateLimitSnapshot]:
        try:
            ws_limited = bool(self._client.is_ws_ratelimited())
        except Exception:
            ws_limited = False
        return [
            {
                "name": "discord.rest",
                "group": "discord",
                "limit": None,
                "window_seconds": None,
                "used": 0,
                "keys": 0,
                "rejected": self.route_hits + self.global_hits,
                "last_rejected_at": self.last_hit_at,
            },
            {
                "name": "discord.gateway",
                "group": "discord",
                "limit": None,
                "window_seconds": None,
                "used": 0,
                "keys": 0,
                "limited": ws_limited,
            },
        ]


def install(client: Client) -> DiscordRateLimitTracker:
    """Attach the tracker to ``discord.http`` and register it for /status."""
    tracker = DiscordRateLimitTracker(client)
    logger = logging.getLogger("discord.http")
    logger.addHandler(tracker)
    # The handler must see WARNING records even if the logger is set quieter.
    if logger.getEffectiveLevel() > logging.WARNING:
        logger.setLevel(logging.WARNING)
    rate_limits.register("discord", tracker.snapshots)
    return tracker
