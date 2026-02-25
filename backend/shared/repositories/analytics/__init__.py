"""AnalyticsRepository — stream session, event, and stats persistence.

Split into three focused mixins to keep each concern testable in isolation:

    _session_mixin  — session lifecycle + VOD sync
    _events_mixin   — stream event recording + chatter stats
    _query_mixin    — aggregation reads (summary, top commands/chatters)

All four in-process caches are defined in _caches.py so every mixin
imports from a single leaf module (no circular-import risk).
"""

from __future__ import annotations

import asyncpg

from shared.repositories.analytics._events_mixin import _AnalyticsEventsMixin
from shared.repositories.analytics._query_mixin import _AnalyticsQueryMixin
from shared.repositories.analytics._session_mixin import _AnalyticsSessionMixin


class AnalyticsRepository(
    _AnalyticsSessionMixin,
    _AnalyticsEventsMixin,
    _AnalyticsQueryMixin,
):
    """Pure SQL operations for stream analytics tables."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
