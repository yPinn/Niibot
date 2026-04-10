"""Unit tests for shared.repositories.message_trigger — MessageTriggerRepository."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.repositories.message_trigger import (
    MessageTriggerRepository,
    _trigger_list_cache,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0)

_TRIGGER_ROW = {
    "id": 1,
    "channel_id": "ch123",
    "trigger_name": "hello",
    "match_type": "contains",
    "pattern": "hello",
    "case_sensitive": False,
    "response": "Hello there!",
    "min_role": "everyone",
    "cooldown": 30,
    "priority": 0,
    "enabled": True,
    "usage_count": 42,
    "created_at": _NOW,
    "updated_at": _NOW,
}


def _make_pool(
    *,
    fetch=None,
    fetchrow=None,
    execute=None,
) -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    if fetch is not None:
        conn.fetch.return_value = fetch
    if fetchrow is not None:
        conn.fetchrow.return_value = fetchrow
    if execute is not None:
        conn.execute.return_value = execute

    # conn.transaction() must return an async context manager, not a coroutine.
    tx_ctx = MagicMock()
    tx_ctx.__aenter__ = AsyncMock(return_value=None)
    tx_ctx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx_ctx)

    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


# ---------------------------------------------------------------------------
# list_enabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestListEnabled:
    async def test_returns_empty_list_when_no_triggers(self):
        _trigger_list_cache.clear()
        pool, _ = _make_pool(fetch=[])
        repo = MessageTriggerRepository(pool)

        result = await repo.list_enabled("ch123")

        assert result == []

    async def test_returns_mapped_trigger_configs(self):
        _trigger_list_cache.clear()
        pool, _ = _make_pool(fetch=[_TRIGGER_ROW])
        repo = MessageTriggerRepository(pool)

        result = await repo.list_enabled("ch123")

        assert len(result) == 1
        t = result[0]
        assert t.id == 1
        assert t.channel_id == "ch123"
        assert t.trigger_name == "hello"
        assert t.match_type == "contains"
        assert t.pattern == "hello"
        assert t.case_sensitive is False
        assert t.response == "Hello there!"
        assert t.min_role == "everyone"
        assert t.cooldown == 30
        assert t.priority == 0
        assert t.enabled is True
        assert t.usage_count == 42

    async def test_result_is_cached_on_second_call(self):
        _trigger_list_cache.clear()
        pool, conn = _make_pool(fetch=[_TRIGGER_ROW])
        repo = MessageTriggerRepository(pool)

        await repo.list_enabled("ch123")
        await repo.list_enabled("ch123")

        assert conn.fetch.call_count == 1

    async def test_different_channels_cached_separately(self):
        _trigger_list_cache.clear()
        pool, conn = _make_pool(fetch=[])
        repo = MessageTriggerRepository(pool)

        await repo.list_enabled("ch_a")
        await repo.list_enabled("ch_b")

        assert conn.fetch.call_count == 2


# ---------------------------------------------------------------------------
# list_all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestListAll:
    async def test_returns_empty_list_when_no_triggers(self):
        pool, _ = _make_pool(fetch=[])
        repo = MessageTriggerRepository(pool)

        result = await repo.list_all("ch123")

        assert result == []

    async def test_returns_all_including_disabled(self):
        disabled_row = {**_TRIGGER_ROW, "id": 2, "trigger_name": "bye", "enabled": False}
        pool, _ = _make_pool(fetch=[_TRIGGER_ROW, disabled_row])
        repo = MessageTriggerRepository(pool)

        result = await repo.list_all("ch123")

        assert len(result) == 2
        names = {t.trigger_name for t in result}
        assert names == {"hello", "bye"}

    async def test_list_all_bypasses_list_enabled_cache(self):
        _trigger_list_cache.clear()
        pool, conn = _make_pool(fetch=[_TRIGGER_ROW])
        repo = MessageTriggerRepository(pool)

        await repo.list_enabled("ch123")
        conn.fetch.reset_mock()

        await repo.list_all("ch123")
        assert conn.fetch.call_count == 1


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUpsert:
    async def test_returns_mapped_trigger_config(self):
        _trigger_list_cache.clear()
        pool, _ = _make_pool(fetchrow=_TRIGGER_ROW)
        repo = MessageTriggerRepository(pool)

        result = await repo.upsert("ch123", "hello")

        assert result.trigger_name == "hello"
        assert result.channel_id == "ch123"

    async def test_invalidates_cache_after_upsert(self):
        _trigger_list_cache.set("trigger_list:ch123", [])
        pool, _ = _make_pool(fetchrow=_TRIGGER_ROW)
        repo = MessageTriggerRepository(pool)

        await repo.upsert("ch123", "hello")

        pool2, conn2 = _make_pool(fetch=[])
        repo2 = MessageTriggerRepository(pool2)
        await repo2.list_enabled("ch123")
        assert conn2.fetch.call_count == 1

    async def test_upsert_passes_all_parameters(self):
        pool, conn = _make_pool(fetchrow=_TRIGGER_ROW)
        repo = MessageTriggerRepository(pool)

        await repo.upsert(
            "ch123",
            "hello",
            match_type="exact",
            pattern="hello world",
            case_sensitive=True,
            response="Hi!",
            min_role="mod",
            cooldown=60,
            priority=10,
            enabled=False,
        )

        # upsert calls fetchrow twice: (1) UPSERT INSERT, (2) SELECT with aliases join
        assert conn.fetchrow.call_count == 2
        # Verify the first call (upsert INSERT) carries all parameters
        upsert_args = conn.fetchrow.call_args_list[0][0]
        assert "ch123" in upsert_args
        assert "hello" in upsert_args
        assert "exact" in upsert_args
        assert "hello world" in upsert_args
        assert True in upsert_args
        assert "Hi!" in upsert_args
        assert "mod" in upsert_args
        assert 60 in upsert_args
        assert 10 in upsert_args
        assert False in upsert_args


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDelete:
    async def test_returns_true_when_row_deleted(self):
        _trigger_list_cache.clear()
        pool, _ = _make_pool(execute="DELETE 1")
        repo = MessageTriggerRepository(pool)

        result = await repo.delete("ch123", "hello")

        assert result is True

    async def test_returns_false_when_nothing_deleted(self):
        _trigger_list_cache.clear()
        pool, _ = _make_pool(execute="DELETE 0")
        repo = MessageTriggerRepository(pool)

        result = await repo.delete("ch123", "nonexistent")

        assert result is False

    async def test_invalidates_cache_on_delete(self):
        _trigger_list_cache.set("trigger_list:ch123", [])
        pool, _ = _make_pool(execute="DELETE 1")
        repo = MessageTriggerRepository(pool)

        await repo.delete("ch123", "hello")

        pool2, conn2 = _make_pool(fetch=[])
        repo2 = MessageTriggerRepository(pool2)
        await repo2.list_enabled("ch123")
        assert conn2.fetch.call_count == 1

    async def test_passes_correct_args_to_execute(self):
        pool, conn = _make_pool(execute="DELETE 1")
        repo = MessageTriggerRepository(pool)

        await repo.delete("ch_x", "my_trigger")

        conn.execute.assert_called_once()
        args = conn.execute.call_args[0]
        assert "ch_x" in args
        assert "my_trigger" in args


# ---------------------------------------------------------------------------
# increment_usage_count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestIncrementUsageCount:
    async def test_calls_execute_with_correct_id(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = MessageTriggerRepository(pool)

        await repo.increment_usage_count(42)

        conn.execute.assert_called_once()
        args = conn.execute.call_args[0]
        assert 42 in args

    async def test_does_not_invalidate_cache(self):
        """increment_usage_count should NOT clear the list cache (hot path)."""
        _trigger_list_cache.set("trigger_list:ch123", ["cached_value"])
        pool, _ = _make_pool(execute="UPDATE 1")
        repo = MessageTriggerRepository(pool)

        await repo.increment_usage_count(1)

        # Cache should still be warm
        assert _trigger_list_cache.get("trigger_list:ch123") == ["cached_value"]


# ---------------------------------------------------------------------------
# invalidate_cache
# ---------------------------------------------------------------------------


class TestInvalidateCache:
    def test_invalidates_cache_for_channel(self):
        _trigger_list_cache.set("trigger_list:ch123", ["some_value"])
        pool = MagicMock()
        repo = MessageTriggerRepository(pool)

        repo.invalidate_cache("ch123")

        from shared.cache import _MISSING

        assert _trigger_list_cache.get("trigger_list:ch123") is _MISSING

    def test_noop_when_nothing_cached(self):
        pool = MagicMock()
        repo = MessageTriggerRepository(pool)

        repo.invalidate_cache("ch_not_cached")
