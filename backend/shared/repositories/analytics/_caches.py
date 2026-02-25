"""Shared in-process caches for AnalyticsRepository mixins.

All four caches live here so every mixin imports from a single
leaf module — no circular-import risk.
"""

from shared.cache import AsyncTTLCache

# Active-session lookup: short TTL — session state changes frequently
_session_cache: AsyncTTLCache = AsyncTTLCache(maxsize=32, ttl=10)

# Aggregation results: 2-minute TTL — tolerable staleness for dashboard reads
_summary_cache: AsyncTTLCache = AsyncTTLCache(maxsize=32, ttl=120)
_top_commands_cache: AsyncTTLCache = AsyncTTLCache(maxsize=32, ttl=120)
_top_chatters_cache: AsyncTTLCache = AsyncTTLCache(maxsize=32, ttl=120)
