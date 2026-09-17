"""Runtime memory/DB gauges shared by the API and twitch bot `/status`
endpoints and their periodic gauge-log loops.

Read-only, synchronous where possible — safe to call from a request handler
or a background loop without touching the DB beyond the pool's own stats.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from shared.cache import iter_caches

if TYPE_CHECKING:
    from shared.database import DatabaseManager


def collect_runtime_gauges(db_manager: DatabaseManager) -> dict[str, Any]:
    """Return `{"db_pool": {...} | None, "caches": {name: {size, stale, maxsize}}}`."""
    return {
        "db_pool": db_manager.pool_stats(),
        "caches": {
            name: {"size": cache.size, "stale": cache.stale_size, "maxsize": cache.maxsize}
            for name, cache in iter_caches()
        },
    }
