"""Contracts for bounded async read-through caching and single-flight loads."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from shared.read_through_cache import AsyncReadThroughCache, CacheLoad


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.mark.asyncio
async def test_fresh_value_is_reused_until_ttl_expires() -> None:
    clock = _Clock()
    loader = AsyncMock(
        side_effect=[
            CacheLoad.cached("first", ttl=10.0),
            CacheLoad.cached("second", ttl=10.0),
        ]
    )
    cache: AsyncReadThroughCache[str, str] = AsyncReadThroughCache(clock=clock)

    assert await cache.get_or_load("key", loader) == "first"
    assert await cache.get_or_load("key", loader) == "first"
    loader.assert_awaited_once()

    clock.advance(10.0)
    assert await cache.get_or_load("key", loader) == "second"
    assert loader.await_count == 2


@pytest.mark.asyncio
async def test_uncached_result_runs_loader_again() -> None:
    loader = AsyncMock(
        side_effect=[
            CacheLoad.uncached("transient"),
            CacheLoad.cached("recovered", ttl=10.0),
        ]
    )
    cache: AsyncReadThroughCache[str, str] = AsyncReadThroughCache()

    assert await cache.get_or_load("key", loader) == "transient"
    assert await cache.get_or_load("key", loader) == "recovered"
    assert loader.await_count == 2


@pytest.mark.asyncio
async def test_concurrent_misses_share_one_loader_task() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def loader() -> CacheLoad[str]:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return CacheLoad.cached("value", ttl=10.0)

    cache: AsyncReadThroughCache[str, str] = AsyncReadThroughCache()
    first = asyncio.create_task(cache.get_or_load("key", loader))
    second = asyncio.create_task(cache.get_or_load("key", loader))
    await started.wait()
    await asyncio.sleep(0)

    assert calls == 1
    release.set()
    assert await asyncio.gather(first, second) == ["value", "value"]


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_cancel_shared_loader() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def loader() -> CacheLoad[str]:
        started.set()
        await release.wait()
        return CacheLoad.cached("value", ttl=10.0)

    cache: AsyncReadThroughCache[str, str] = AsyncReadThroughCache()
    cancelled = asyncio.create_task(cache.get_or_load("key", loader))
    survivor = asyncio.create_task(cache.get_or_load("key", loader))
    await started.wait()
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled

    release.set()
    assert await survivor == "value"


@pytest.mark.asyncio
async def test_loader_error_is_not_cached_or_left_in_flight() -> None:
    loader = AsyncMock(
        side_effect=[
            RuntimeError("provider failed"),
            CacheLoad.cached("recovered", ttl=10.0),
        ]
    )
    cache: AsyncReadThroughCache[str, str] = AsyncReadThroughCache()

    with pytest.raises(RuntimeError, match="provider failed"):
        await cache.get_or_load("key", loader)
    assert await cache.get_or_load("key", loader) == "recovered"
    assert loader.await_count == 2


@pytest.mark.asyncio
async def test_cache_evicts_least_recently_used_entry_at_capacity() -> None:
    cache: AsyncReadThroughCache[str, str] = AsyncReadThroughCache(max_entries=2)
    loaders = {
        key: AsyncMock(return_value=CacheLoad.cached(key, ttl=10.0)) for key in ("a", "b", "c")
    }

    await cache.get_or_load("a", loaders["a"])
    await cache.get_or_load("b", loaders["b"])
    await cache.get_or_load("a", loaders["a"])
    await cache.get_or_load("c", loaders["c"])
    await cache.get_or_load("b", loaders["b"])

    assert loaders["a"].await_count == 1
    assert loaders["b"].await_count == 2
    assert loaders["c"].await_count == 1


def test_invalid_cache_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_entries"):
        AsyncReadThroughCache(max_entries=0)
    with pytest.raises(ValueError, match="ttl"):
        CacheLoad.cached("value", ttl=0.0)
