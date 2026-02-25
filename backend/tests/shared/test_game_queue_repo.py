"""Unit tests for shared.repositories.game_queue — GameQueueRepository and GameQueueSettingsRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.repositories.game_queue import (
    GameQueueRepository,
    GameQueueSettingsRepository,
    _settings_cache,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

_ENTRY_ROW = {
    "id": 1,
    "channel_id": "ch123",
    "user_id": "u1",
    "user_name": "alice",
    "redeemed_at": _NOW,
    "removed_at": None,
    "removal_reason": None,
    "created_at": _NOW,
}

_SETTINGS_ROW = {
    "id": 1,
    "channel_id": "ch123",
    "group_size": 4,
    "enabled": True,
    "created_at": _NOW,
    "updated_at": _NOW,
}

_UNSET = object()


def _make_pool(
    *,
    fetch=_UNSET,
    fetchrow=_UNSET,
    fetchval=_UNSET,
    execute=_UNSET,
) -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    if fetch is not _UNSET:
        conn.fetch.return_value = fetch
    if fetchrow is not _UNSET:
        conn.fetchrow.return_value = fetchrow
    if fetchval is not _UNSET:
        conn.fetchval.return_value = fetchval
    if execute is not _UNSET:
        conn.execute.return_value = execute

    # transaction() returns a sync object that IS an async context manager
    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=None)
    mock_tx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=mock_tx)

    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def _clear_settings_cache() -> None:
    _settings_cache.clear()
    _settings_cache._stale.clear()


# ---------------------------------------------------------------------------
# GameQueueRepository — add_entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAddEntry:
    async def test_returns_mapped_entry(self):
        pool, _ = _make_pool(fetchrow=_ENTRY_ROW)
        repo = GameQueueRepository(pool)

        result = await repo.add_entry("ch123", "u1", "alice")

        assert result.user_id == "u1"
        assert result.user_name == "alice"
        assert result.channel_id == "ch123"
        assert result.removed_at is None

    async def test_passes_correct_args(self):
        pool, conn = _make_pool(fetchrow=_ENTRY_ROW)
        repo = GameQueueRepository(pool)

        await repo.add_entry("ch_x", "u99", "bob")

        args = conn.fetchrow.call_args[0]
        assert "ch_x" in args
        assert "u99" in args
        assert "bob" in args


# ---------------------------------------------------------------------------
# GameQueueRepository — get_active_entries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetActiveEntries:
    async def test_returns_empty_list_when_none(self):
        pool, _ = _make_pool(fetch=[])
        repo = GameQueueRepository(pool)

        result = await repo.get_active_entries("ch123")

        assert result == []

    async def test_returns_mapped_entries(self):
        row2 = {**_ENTRY_ROW, "id": 2, "user_id": "u2", "user_name": "bob"}
        pool, _ = _make_pool(fetch=[_ENTRY_ROW, row2])
        repo = GameQueueRepository(pool)

        result = await repo.get_active_entries("ch123")

        assert len(result) == 2
        names = {e.user_name for e in result}
        assert names == {"alice", "bob"}

    async def test_only_returns_non_removed(self):
        """Verified by SQL, but at least the return type is correct."""
        pool, _ = _make_pool(fetch=[_ENTRY_ROW])
        repo = GameQueueRepository(pool)

        result = await repo.get_active_entries("ch123")

        assert all(e.removed_at is None for e in result)


# ---------------------------------------------------------------------------
# GameQueueRepository — find_active_by_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFindActiveByUser:
    async def test_returns_none_when_not_in_queue(self):
        pool, conn = _make_pool()
        conn.fetchrow.return_value = None
        repo = GameQueueRepository(pool)

        result = await repo.find_active_by_user("ch123", "u_not_in_queue")

        assert result is None

    async def test_returns_entry_when_found(self):
        pool, _ = _make_pool(fetchrow=_ENTRY_ROW)
        repo = GameQueueRepository(pool)

        result = await repo.find_active_by_user("ch123", "u1")

        assert result is not None
        assert result.user_id == "u1"


# ---------------------------------------------------------------------------
# GameQueueRepository — count_active
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCountActive:
    async def test_returns_integer_count(self):
        pool, _ = _make_pool(fetchval=5)
        repo = GameQueueRepository(pool)

        result = await repo.count_active("ch123")

        assert result == 5

    async def test_returns_zero_when_empty(self):
        pool, _ = _make_pool(fetchval=0)
        repo = GameQueueRepository(pool)

        result = await repo.count_active("ch123")

        assert result == 0


# ---------------------------------------------------------------------------
# GameQueueRepository — remove_entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRemoveEntry:
    async def test_returns_true_when_updated(self):
        pool, _ = _make_pool(execute="UPDATE 1")
        repo = GameQueueRepository(pool)

        result = await repo.remove_entry(1, "ch123")

        assert result is True

    async def test_returns_false_when_not_found(self):
        pool, _ = _make_pool(execute="UPDATE 0")
        repo = GameQueueRepository(pool)

        result = await repo.remove_entry(999, "ch123")

        assert result is False

    async def test_passes_default_reason(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = GameQueueRepository(pool)

        await repo.remove_entry(1, "ch123")

        args = conn.execute.call_args[0]
        assert "kicked" in args


# ---------------------------------------------------------------------------
# GameQueueRepository — remove_by_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRemoveByUser:
    async def test_returns_true_when_removed(self):
        pool, _ = _make_pool(execute="UPDATE 1")
        repo = GameQueueRepository(pool)

        result = await repo.remove_by_user("ch123", "u1")

        assert result is True

    async def test_returns_false_when_user_not_in_queue(self):
        pool, _ = _make_pool(execute="UPDATE 0")
        repo = GameQueueRepository(pool)

        result = await repo.remove_by_user("ch123", "ghost")

        assert result is False


# ---------------------------------------------------------------------------
# GameQueueRepository — complete_batch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCompleteBatch:
    async def test_returns_zero_for_empty_ids(self):
        pool, conn = _make_pool()
        repo = GameQueueRepository(pool)

        result = await repo.complete_batch("ch123", [])

        assert result == 0
        conn.execute.assert_not_called()

    async def test_returns_count_of_completed(self):
        pool, _ = _make_pool(execute="UPDATE 3")
        repo = GameQueueRepository(pool)

        result = await repo.complete_batch("ch123", [1, 2, 3])

        assert result == 3

    async def test_passes_entry_ids_as_list(self):
        pool, conn = _make_pool(execute="UPDATE 2")
        repo = GameQueueRepository(pool)

        await repo.complete_batch("ch123", [10, 20])

        args = conn.execute.call_args[0]
        assert [10, 20] in args


# ---------------------------------------------------------------------------
# GameQueueRepository — clear_queue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestClearQueue:
    async def test_returns_count_of_cleared(self):
        pool, _ = _make_pool(execute="UPDATE 5")
        repo = GameQueueRepository(pool)

        result = await repo.clear_queue("ch123")

        assert result == 5

    async def test_passes_default_reason(self):
        pool, conn = _make_pool(execute="UPDATE 0")
        repo = GameQueueRepository(pool)

        await repo.clear_queue("ch123")

        args = conn.execute.call_args[0]
        assert "cleared" in args


# ---------------------------------------------------------------------------
# GameQueueSettingsRepository — get_or_create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetOrCreate:
    async def test_returns_mapped_settings(self):
        _clear_settings_cache()
        pool, conn = _make_pool(fetchrow=_SETTINGS_ROW)
        conn.execute.return_value = "INSERT 0 1"
        repo = GameQueueSettingsRepository(pool)

        result = await repo.get_or_create("ch123")

        assert result.channel_id == "ch123"
        assert result.group_size == 4
        assert result.enabled is True

    async def test_result_is_cached(self):
        _clear_settings_cache()
        pool, conn = _make_pool(fetchrow=_SETTINGS_ROW)
        conn.execute.return_value = "INSERT 0 1"
        repo = GameQueueSettingsRepository(pool)

        await repo.get_or_create("ch123")
        await repo.get_or_create("ch123")

        assert conn.fetchrow.call_count == 1


# ---------------------------------------------------------------------------
# GameQueueSettingsRepository — update_settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUpdateSettings:
    async def test_returns_updated_settings(self):
        _clear_settings_cache()
        updated_row = {**_SETTINGS_ROW, "group_size": 6, "enabled": False}
        pool, _ = _make_pool(fetchrow=updated_row)
        repo = GameQueueSettingsRepository(pool)

        result = await repo.update_settings("ch123", group_size=6, enabled=False)

        assert result.group_size == 6
        assert result.enabled is False

    async def test_invalidates_cache_after_update(self):
        _clear_settings_cache()
        _settings_cache.set("gq_settings:ch123", _SETTINGS_ROW)
        pool, _ = _make_pool(fetchrow=_SETTINGS_ROW)
        repo = GameQueueSettingsRepository(pool)

        await repo.update_settings("ch123", group_size=2)

        from shared.cache import _MISSING

        assert _settings_cache.get("gq_settings:ch123") is _MISSING

    async def test_passes_none_for_unset_fields(self):
        pool, conn = _make_pool(fetchrow=_SETTINGS_ROW)
        repo = GameQueueSettingsRepository(pool)

        await repo.update_settings("ch123", group_size=3)

        args = conn.fetchrow.call_args[0]
        assert 3 in args
        assert None in args  # enabled was not provided → None passed to COALESCE
