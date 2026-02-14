"""In-process TTL cache with stale fallback for Niibot services.

Uses cachetools.TTLCache for zero-infrastructure caching.
Each service creates its own cache instances — no cross-process sharing.

When the database is unavailable, read operations fall back to stale
(TTL-expired) cached values so the bot keeps running.
"""

import asyncio
import functools
import logging
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, TypeVar

from cachetools import TTLCache  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Sentinel object to distinguish "not in cache" from cached None values
_MISSING = object()

F = TypeVar("F", bound=Callable[..., Any])


class AsyncTTLCache:
    """Async-aware TTL cache with a stale fallback store.

    Two tiers:
      1. ``_cache`` (TTLCache) — fresh data, governed by *ttl*.
      2. ``_stale`` (OrderedDict, LRU, bounded by *maxsize*) — last-known-good
         values that survive TTL expiry.  Used **only** when the upstream source
         (DB) is unreachable.
    """

    def __init__(self, maxsize: int = 128, ttl: float = 60.0):
        self._maxsize = maxsize
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._stale: OrderedDict[str, Any] = OrderedDict()
        self._locks: dict[str, asyncio.Lock] = {}

    # --- lock management (bounded) ---

    def _get_lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
            # Prune locks that no longer have a corresponding stale entry
            if len(self._locks) > self._maxsize * 2:
                stale_keys = set(self._stale)
                for k in list(self._locks):
                    if k not in stale_keys and k not in self._cache:
                        del self._locks[k]
        return self._locks[key]

    # --- primary (fresh) operations ---

    def get(self, key: str) -> Any:
        """Return fresh value or ``_MISSING``."""
        return self._cache.get(key, _MISSING)

    def set(self, key: str, value: Any) -> None:
        """Write to both fresh cache and stale store."""
        self._cache[key] = value
        # Update stale store (LRU: move to end)
        self._stale[key] = value
        self._stale.move_to_end(key)
        while len(self._stale) > self._maxsize:
            self._stale.popitem(last=False)

    def invalidate(self, key: str) -> None:
        """Remove from fresh cache; stale store keeps the value."""
        self._cache.pop(key, None)

    def clear(self) -> None:
        """Clear fresh cache; stale store is preserved."""
        self._cache.clear()

    # --- stale fallback ---

    def get_stale(self, key: str) -> Any:
        """Return last-known-good value or ``_MISSING``."""
        value = self._stale.get(key, _MISSING)
        if value is not _MISSING:
            self._stale.move_to_end(key)  # refresh LRU position
        return value

    @property
    def size(self) -> int:
        return len(self._cache)

    @property
    def stale_size(self) -> int:
        return len(self._stale)


def cached(
    cache: AsyncTTLCache,
    key_func: Callable[..., str],
    *,
    retry: int = 3,
):
    """Decorator for caching async function results with DB resilience.

    Parameters
    ----------
    cache : AsyncTTLCache
        The cache instance to use.
    key_func : callable
        Receives the same ``(*args, **kwargs)`` as the decorated function
        and returns the cache key string.
    retry : int
        Max number of attempts on DB failure (default 3).

    Behaviour on DB failure
    -----------------------
    After *retry* attempts, the decorator checks the **stale** store.
    If a stale value exists it is returned with a warning log.
    Otherwise the original exception is re-raised.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_key = key_func(*args, **kwargs)

            # 1. Fast path — fresh cache hit
            result = cache.get(cache_key)
            if result is not _MISSING:
                return result

            # 2. Slow path with lock (double-checked locking)
            async with cache._get_lock(cache_key):
                result = cache.get(cache_key)
                if result is not _MISSING:
                    return result

                # 3. Try DB with retry
                last_exc: BaseException | None = None
                for attempt in range(1, retry + 1):
                    try:
                        result = await func(*args, **kwargs)
                        cache.set(cache_key, result)
                        return result
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        last_exc = exc
                        if attempt < retry:
                            delay = 1.0 * attempt
                            logger.warning(
                                "DB attempt %d/%d failed for %s: %s, retrying in %.1fs…",
                                attempt,
                                retry,
                                cache_key,
                                type(exc).__name__,
                                delay,
                            )
                            await asyncio.sleep(delay)

                # 4. All retries exhausted — try stale fallback
                stale = cache.get_stale(cache_key)
                if stale is not _MISSING:
                    logger.warning(
                        "Returning stale data for %s (%s)",
                        cache_key,
                        type(last_exc).__name__,
                    )
                    return stale

                # 5. No stale data — propagate the error
                raise last_exc  # type: ignore[misc]

        wrapper.cache = cache  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
