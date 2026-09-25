"""Bounded, cancellation-safe async read-through caching primitives."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable
from dataclasses import dataclass
from weakref import WeakKeyDictionary


@dataclass(frozen=True, slots=True)
class CacheLoad[V]:
    """A loader result plus an explicit decision about freshness."""

    value: V
    ttl: float | None

    @classmethod
    def cached(cls, value: V, *, ttl: float) -> CacheLoad[V]:
        if ttl <= 0:
            raise ValueError("cache ttl must be positive")
        return cls(value=value, ttl=ttl)

    @classmethod
    def uncached(cls, value: V) -> CacheLoad[V]:
        return cls(value=value, ttl=None)


@dataclass(frozen=True, slots=True)
class _Entry[V]:
    value: V
    expires_at: float


class AsyncReadThroughCache[K: Hashable, V]:
    """Collapse concurrent misses and retain only loader-approved values."""

    def __init__(
        self,
        *,
        max_entries: int = 512,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[K, _Entry[V]] = OrderedDict()
        self._inflight: dict[K, asyncio.Task[V]] = {}

    async def get_or_load(
        self,
        key: K,
        loader: Callable[[], Awaitable[CacheLoad[V]]],
    ) -> V:
        now = self._clock()
        cached = self._entries.get(key)
        if cached is not None:
            if cached.expires_at > now:
                self._entries.move_to_end(key)
                return cached.value
            del self._entries[key]

        task = self._inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._load(key, loader))
            self._inflight[key] = task
        # One cancelled request must not cancel the provider call shared by
        # every other waiter for this key.
        return await asyncio.shield(task)

    async def _load(
        self,
        key: K,
        loader: Callable[[], Awaitable[CacheLoad[V]]],
    ) -> V:
        current = asyncio.current_task()
        try:
            loaded = await loader()
            if loaded.ttl is not None:
                self._entries[key] = _Entry(
                    value=loaded.value,
                    expires_at=self._clock() + loaded.ttl,
                )
                self._entries.move_to_end(key)
                while len(self._entries) > self._max_entries:
                    self._entries.popitem(last=False)
            return loaded.value
        finally:
            if self._inflight.get(key) is current:
                del self._inflight[key]

    def clear(self) -> None:
        """Drop retained values without cancelling in-flight provider calls."""
        self._entries.clear()


class LoopLocalReadThroughCache[K: Hashable, V]:
    """Provide one cache per event loop, avoiding cross-loop task ownership."""

    def __init__(self, *, max_entries: int = 512) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._caches: WeakKeyDictionary[
            asyncio.AbstractEventLoop,
            AsyncReadThroughCache[K, V],
        ] = WeakKeyDictionary()

    async def get_or_load(
        self,
        key: K,
        loader: Callable[[], Awaitable[CacheLoad[V]]],
    ) -> V:
        loop = asyncio.get_running_loop()
        cache = self._caches.get(loop)
        if cache is None:
            cache = AsyncReadThroughCache(max_entries=self._max_entries)
            self._caches[loop] = cache
        return await cache.get_or_load(key, loader)

    def clear(self) -> None:
        for cache in self._caches.values():
            cache.clear()
