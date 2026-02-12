"""In-process TTL cache utilities for Niibot services.

Uses cachetools.TTLCache for zero-infrastructure caching.
Each service creates its own cache instances — no cross-process sharing.
"""

import asyncio
import functools
import logging
from collections.abc import Callable
from typing import Any, Protocol, TypeVar, cast

from cachetools import TTLCache  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Sentinel object to distinguish "not in cache" from cached None values
_MISSING = object()


# Protocol for typed cached function
class CachedFunction(Protocol):
    __call__: Any
    cache: "AsyncTTLCache"


# Generic type var for decorator
F = TypeVar("F", bound=Callable[..., Any])


class AsyncTTLCache:
    """Async-aware TTL cache wrapper around cachetools.TTLCache."""

    def __init__(self, maxsize: int = 128, ttl: float = 60.0):
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def get(self, key: str) -> Any:
        return self._cache.get(key, _MISSING)

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = value

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()
        self._locks.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


def cached(cache: AsyncTTLCache, key_func: Callable[..., str]):
    """Decorator for caching async function results."""

    def decorator(func: F) -> CachedFunction:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = key_func(*args, **kwargs)

            # Fast path
            result = cache.get(cache_key)
            if result is not _MISSING:
                return result

            # Slow path with lock (Double-checked locking)
            async with cache._get_lock(cache_key):
                result = cache.get(cache_key)
                if result is not _MISSING:
                    return result

                result = await func(*args, **kwargs)
                if result is not None:
                    cache.set(cache_key, result)
                return result

        # Cast and attach cache attribute
        narrowed_wrapper = cast(CachedFunction, wrapper)
        narrowed_wrapper.cache = cache
        return narrowed_wrapper

    return decorator
