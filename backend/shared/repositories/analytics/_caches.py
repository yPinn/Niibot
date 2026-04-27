"""Shared in-process caches for AnalyticsRepository mixins.

All four caches live here so every mixin imports from a single
leaf module — no circular-import risk.
"""

from shared.cache import AsyncTTLCache

# Active-session lookup: short TTL — session state changes frequently
_session_cache: AsyncTTLCache = AsyncTTLCache(maxsize=32, ttl=10)

# Aggregation results: 5-minute TTL — matches HTTP Cache-Control and frontend apiCache TTL
_summary_cache: AsyncTTLCache = AsyncTTLCache(maxsize=32, ttl=300)
_top_commands_cache: AsyncTTLCache = AsyncTTLCache(maxsize=32, ttl=300)
_top_chatters_cache: AsyncTTLCache = AsyncTTLCache(maxsize=32, ttl=300)
