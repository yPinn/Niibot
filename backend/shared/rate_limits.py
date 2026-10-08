"""In-process registry of rate limits, surfaced in each service's `/status`.

Anything that throttles — our own inbound `RateLimiter`s, the Twitch egress
gates, provider-reported budgets — registers a provider returning snapshots in
one shape, so the admin Monitor renders every service's limits uniformly.

Snapshots are read-only and cheap (no I/O); a provider that raises is skipped
rather than breaking the status endpoint it is part of.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Literal, NotRequired, TypedDict

LOGGER = logging.getLogger(__name__)

RateLimitGroup = Literal["inbound", "twitch", "discord", "egress"]


class ProviderBudget(TypedDict):
    """A budget the provider itself reported (e.g. Twitch `Ratelimit-*`)."""

    limit: int | None
    remaining: int | None
    reset_at: float | None  # epoch seconds


class RateLimitSnapshot(TypedDict):
    name: str
    group: RateLimitGroup
    limit: int | None  # calls allowed per window, per key
    window_seconds: float | None
    used: int  # the busiest key's calls in the current window
    keys: int  # keys (callers / buckets) active in the window
    queued: NotRequired[int]  # waiters held back (egress gates)
    blocked_seconds: NotRequired[float]  # longest provider-imposed pause left
    limited: NotRequired[bool]  # throttled right now (a state, not a window count)
    allowed: NotRequired[int]  # totals since process start
    rejected: NotRequired[int]
    last_rejected_at: NotRequired[float | None]  # epoch seconds
    provider: NotRequired[ProviderBudget | None]


SnapshotProvider = Callable[[], list[RateLimitSnapshot]]

_providers: dict[str, SnapshotProvider] = {}


def register(key: str, provider: SnapshotProvider) -> None:
    """Register (or replace) a snapshot provider under a unique key."""
    _providers[key] = provider


def unregister(key: str) -> None:
    _providers.pop(key, None)


def collect_rate_limits() -> list[RateLimitSnapshot]:
    snapshots: list[RateLimitSnapshot] = []
    for key, provider in list(_providers.items()):
        try:
            snapshots.extend(provider())
        except Exception:
            LOGGER.exception("Rate limit snapshot provider %s failed", key)
    return sorted(snapshots, key=lambda s: (s["group"], s["name"]))
