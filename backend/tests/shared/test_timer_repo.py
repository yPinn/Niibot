"""Unit tests for shared.repositories.timer — TimerConfigRepository."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.repositories.timer import TimerConfigRepository, _timer_list_cache

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0)

_TIMER_ROW = {
    "id": 1,
    "channel_id": "ch123",
    "timer_name": "uptime",
    "interval_seconds": 300,
    "min_lines": 5,
    "message_template": "Stream has been live for {uptime}",
    "enabled": True,
    "created_at": _NOW,
    "updated_at": _NOW,
}


def _make_pool(
    *,
    fetch=None,
    fetchrow=None,
    execute=None,
) -> tuple[MagicMock, AsyncMock]:
    """Return (pool, conn) with preset mock return values."""
    conn = AsyncMock()
    if fetch is not None:
        conn.fetch.return_value = fetch
    if fetchrow is not None:
        conn.fetchrow.return_value = fetchrow
    if execute is not None:
        conn.execute.return_value = execute

    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


# ---------------------------------------------------------------------------
# list_enabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestListEnabled:
    async def test_returns_empty_list_when_no_timers(self):
        _timer_list_cache.clear()
        pool, _ = _make_pool(fetch=[])
        repo = TimerConfigRepository(pool)

        result = await repo.list_enabled("ch123")

        assert result == []

    async def test_returns_mapped_timer_configs(self):
        _timer_list_cache.clear()
        pool, _ = _make_pool(fetch=[_TIMER_ROW])
        repo = TimerConfigRepository(pool)

        result = await repo.list_enabled("ch123")

        assert len(result) == 1
        t = result[0]
        assert t.id == 1
        assert t.channel_id == "ch123"
        assert t.timer_name == "uptime"
        assert t.interval_seconds == 300
        assert t.min_lines == 5
        assert t.enabled is True

    async def test_result_is_cached_on_second_call(self):
        _timer_list_cache.clear()
        pool, conn = _make_pool(fetch=[_TIMER_ROW])
        repo = TimerConfigRepository(pool)

        await repo.list_enabled("ch123")
        await repo.list_enabled("ch123")

        # DB should only be hit once (second call uses cache)
        assert conn.fetch.call_count == 1

    async def test_different_channels_cached_separately(self):
        _timer_list_cache.clear()
        pool, conn = _make_pool(fetch=[])
        repo = TimerConfigRepository(pool)

        await repo.list_enabled("ch_a")
        await repo.list_enabled("ch_b")

        assert conn.fetch.call_count == 2


# ---------------------------------------------------------------------------
# list_all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestListAll:
    async def test_returns_empty_list_when_no_timers(self):
        pool, _ = _make_pool(fetch=[])
        repo = TimerConfigRepository(pool)

        result = await repo.list_all("ch123")

        assert result == []

    async def test_returns_all_timers_including_disabled(self):
        disabled_row = {**_TIMER_ROW, "id": 2, "timer_name": "socials", "enabled": False}
        pool, _ = _make_pool(fetch=[_TIMER_ROW, disabled_row])
        repo = TimerConfigRepository(pool)

        result = await repo.list_all("ch123")

        assert len(result) == 2
        assert result[0].enabled is True
        assert result[1].enabled is False

    async def test_list_all_bypasses_list_enabled_cache(self):
        """list_all does not use the list-enabled cache."""
        _timer_list_cache.clear()
        pool, conn = _make_pool(fetch=[_TIMER_ROW])
        repo = TimerConfigRepository(pool)

        # Warm up list_enabled cache
        await repo.list_enabled("ch123")
        conn.fetch.reset_mock()

        # list_all should still hit DB
        await repo.list_all("ch123")
        assert conn.fetch.call_count == 1


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUpsert:
    async def test_returns_mapped_timer_config(self):
        _timer_list_cache.clear()
        pool, _ = _make_pool(fetchrow=_TIMER_ROW)
        repo = TimerConfigRepository(pool)

        result = await repo.upsert("ch123", "uptime", interval_seconds=300)

        assert result.timer_name == "uptime"
        assert result.channel_id == "ch123"
        assert result.interval_seconds == 300

    async def test_invalidates_cache_after_upsert(self):
        _timer_list_cache.set("timer_list:ch123", [])  # seed cache
        pool, _ = _make_pool(fetchrow=_TIMER_ROW, fetch=[_TIMER_ROW])
        repo = TimerConfigRepository(pool)

        await repo.upsert("ch123", "uptime")

        # Cache should be gone — next read hits DB
        conn2 = AsyncMock()
        conn2.fetch.return_value = [_TIMER_ROW]
        pool2 = MagicMock()
        pool2.acquire.return_value.__aenter__ = AsyncMock(return_value=conn2)
        pool2.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        repo2 = TimerConfigRepository(pool2)
        await repo2.list_enabled("ch123")
        assert conn2.fetch.call_count == 1

    async def test_upsert_passes_all_parameters(self):
        pool, conn = _make_pool(fetchrow=_TIMER_ROW)
        repo = TimerConfigRepository(pool)

        await repo.upsert(
            "ch123",
            "uptime",
            interval_seconds=600,
            min_lines=10,
            message_template="!uptime",
            enabled=False,
        )

        conn.fetchrow.assert_called_once()
        call_args = conn.fetchrow.call_args[0]
        assert "ch123" in call_args
        assert "uptime" in call_args
        assert 600 in call_args
        assert 10 in call_args


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDelete:
    async def test_returns_true_when_row_deleted(self):
        _timer_list_cache.clear()
        pool, _ = _make_pool(execute="DELETE 1")
        repo = TimerConfigRepository(pool)

        result = await repo.delete("ch123", "uptime")

        assert result is True

    async def test_returns_false_when_nothing_deleted(self):
        _timer_list_cache.clear()
        pool, _ = _make_pool(execute="DELETE 0")
        repo = TimerConfigRepository(pool)

        result = await repo.delete("ch123", "nonexistent")

        assert result is False

    async def test_invalidates_cache_on_delete(self):
        _timer_list_cache.set("timer_list:ch123", [])
        pool, _ = _make_pool(execute="DELETE 1")
        repo = TimerConfigRepository(pool)

        await repo.delete("ch123", "uptime")

        # Cache invalidated — next list_enabled call hits DB
        pool2, conn2 = _make_pool(fetch=[])
        repo2 = TimerConfigRepository(pool2)
        await repo2.list_enabled("ch123")
        assert conn2.fetch.call_count == 1

    async def test_passes_correct_args_to_execute(self):
        pool, conn = _make_pool(execute="DELETE 1")
        repo = TimerConfigRepository(pool)

        await repo.delete("ch_x", "my_timer")

        conn.execute.assert_called_once()
        call_args = conn.execute.call_args[0]
        assert "ch_x" in call_args
        assert "my_timer" in call_args


# ---------------------------------------------------------------------------
# invalidate_cache
# ---------------------------------------------------------------------------


class TestInvalidateCache:
    def test_invalidates_cache_for_channel(self):
        _timer_list_cache.set("timer_list:ch123", ["some_value"])
        pool = MagicMock()
        repo = TimerConfigRepository(pool)

        repo.invalidate_cache("ch123")

        from shared.cache import _MISSING

        assert _timer_list_cache.get("timer_list:ch123") is _MISSING

    def test_noop_when_nothing_cached(self):
        pool = MagicMock()
        repo = TimerConfigRepository(pool)

        # Must not raise
        repo.invalidate_cache("ch_not_in_cache")
