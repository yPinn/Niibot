"""Unit tests for shared.repositories.birthday — BirthdayRepository."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.repositories.birthday import (
    BirthdayRepository,
    _all_enabled_cache,
    _birthday_cache,
    _settings_cache,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
_TODAY = date(2024, 6, 1)

_BIRTHDAY_ROW = {
    "user_id": 1001,
    "month": 6,
    "day": 15,
    "year": 1995,
    "created_at": _NOW,
    "updated_at": _NOW,
}

_SETTINGS_ROW = {
    "guild_id": 999,
    "channel_id": 111,
    "role_id": 222,
    "message_template": "Happy birthday!",
    "last_notified_date": None,
    "enabled": True,
    "created_at": _NOW,
    "updated_at": _NOW,
}

_UNSET = object()


def _make_pool(
    *,
    fetch=_UNSET,
    fetchrow=_UNSET,
    execute=_UNSET,
) -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    if fetch is not _UNSET:
        conn.fetch.return_value = fetch
    if fetchrow is not _UNSET:
        conn.fetchrow.return_value = fetchrow
    if execute is not _UNSET:
        conn.execute.return_value = execute

    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def _clear_caches() -> None:
    for cache in (_birthday_cache, _settings_cache, _all_enabled_cache):
        cache.clear()
        cache._stale.clear()


# ---------------------------------------------------------------------------
# get_birthday
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetBirthday:
    async def test_returns_none_when_not_found(self):
        _clear_caches()
        pool, conn = _make_pool()
        conn.fetchrow.return_value = None
        repo = BirthdayRepository(pool)

        result = await repo.get_birthday(1001)

        assert result is None

    async def test_returns_birthday_when_found(self):
        _clear_caches()
        pool, _ = _make_pool(fetchrow=_BIRTHDAY_ROW)
        repo = BirthdayRepository(pool)

        result = await repo.get_birthday(1001)

        assert result is not None
        assert result.user_id == 1001
        assert result.month == 6
        assert result.day == 15
        assert result.year == 1995

    async def test_result_is_cached(self):
        _clear_caches()
        pool, conn = _make_pool(fetchrow=_BIRTHDAY_ROW)
        repo = BirthdayRepository(pool)

        await repo.get_birthday(1001)
        await repo.get_birthday(1001)

        assert conn.fetchrow.call_count == 1


# ---------------------------------------------------------------------------
# upsert_birthday
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUpsertBirthday:
    async def test_invalidates_birthday_cache(self):
        _birthday_cache.set("bday:1001", _BIRTHDAY_ROW)
        pool, _ = _make_pool(execute="INSERT 0 1")
        repo = BirthdayRepository(pool)

        await repo.upsert_birthday(1001, 6, 15)

        from shared.cache import _MISSING

        assert _birthday_cache.get("bday:1001") is _MISSING

    async def test_passes_all_fields(self):
        pool, conn = _make_pool(execute="INSERT 0 1")
        repo = BirthdayRepository(pool)

        await repo.upsert_birthday(1001, 6, 15, year=1995)

        args = conn.execute.call_args[0]
        assert 1001 in args
        assert 6 in args
        assert 15 in args
        assert 1995 in args


# ---------------------------------------------------------------------------
# delete_birthday
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDeleteBirthday:
    async def test_returns_true_when_deleted(self):
        pool, _ = _make_pool(execute="DELETE 1")
        repo = BirthdayRepository(pool)

        result = await repo.delete_birthday(1001)

        assert result is True

    async def test_returns_false_when_not_found(self):
        pool, _ = _make_pool(execute="DELETE 0")
        repo = BirthdayRepository(pool)

        result = await repo.delete_birthday(9999)

        assert result is False

    async def test_invalidates_cache(self):
        _birthday_cache.set("bday:1001", _BIRTHDAY_ROW)
        pool, _ = _make_pool(execute="DELETE 1")
        repo = BirthdayRepository(pool)

        await repo.delete_birthday(1001)

        from shared.cache import _MISSING

        assert _birthday_cache.get("bday:1001") is _MISSING


# ---------------------------------------------------------------------------
# Subscription operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSubscriptions:
    async def test_exists_returns_true_when_found(self):
        pool, _ = _make_pool(fetchrow={"1": 1})
        repo = BirthdayRepository(pool)

        result = await repo.exists_subscription(999, 1001)

        assert result is True

    async def test_exists_returns_false_when_not_found(self):
        pool, conn = _make_pool()
        conn.fetchrow.return_value = None
        repo = BirthdayRepository(pool)

        result = await repo.exists_subscription(999, 9999)

        assert result is False

    async def test_delete_subscription_returns_true(self):
        pool, _ = _make_pool(execute="DELETE 1")
        repo = BirthdayRepository(pool)

        result = await repo.delete_subscription(999, 1001)

        assert result is True

    async def test_delete_subscription_returns_false(self):
        pool, _ = _make_pool(execute="DELETE 0")
        repo = BirthdayRepository(pool)

        result = await repo.delete_subscription(999, 9999)

        assert result is False


# ---------------------------------------------------------------------------
# Settings operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetSettings:
    async def test_returns_none_when_not_configured(self):
        _clear_caches()
        pool, conn = _make_pool()
        conn.fetchrow.return_value = None
        repo = BirthdayRepository(pool)

        result = await repo.get_settings(999)

        assert result is None

    async def test_returns_settings_when_found(self):
        _clear_caches()
        pool, _ = _make_pool(fetchrow=_SETTINGS_ROW)
        repo = BirthdayRepository(pool)

        result = await repo.get_settings(999)

        assert result is not None
        assert result.guild_id == 999
        assert result.channel_id == 111
        assert result.enabled is True

    async def test_result_is_cached(self):
        _clear_caches()
        pool, conn = _make_pool(fetchrow=_SETTINGS_ROW)
        repo = BirthdayRepository(pool)

        await repo.get_settings(999)
        await repo.get_settings(999)

        assert conn.fetchrow.call_count == 1


@pytest.mark.asyncio
class TestCreateSettings:
    async def test_uses_template_branch_when_provided(self):
        pool, conn = _make_pool(execute="INSERT 0 1")
        repo = BirthdayRepository(pool)

        await repo.create_settings(999, 111, 222, message_template="Happy bday!")

        args = conn.execute.call_args[0]
        assert "Happy bday!" in args

    async def test_uses_no_template_branch_when_omitted(self):
        pool, conn = _make_pool(execute="INSERT 0 1")
        repo = BirthdayRepository(pool)

        await repo.create_settings(999, 111, 222)

        conn.execute.assert_called_once()
        args = conn.execute.call_args[0]
        assert 999 in args
        assert 111 in args
        assert 222 in args

    async def test_invalidates_caches(self):
        _settings_cache.set("settings:999", _SETTINGS_ROW)
        pool, _ = _make_pool(execute="INSERT 0 1")
        repo = BirthdayRepository(pool)

        await repo.create_settings(999, 111, 222)

        from shared.cache import _MISSING

        assert _settings_cache.get("settings:999") is _MISSING


@pytest.mark.asyncio
class TestUpdateSettings:
    async def test_does_nothing_when_no_fields_provided(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = BirthdayRepository(pool)

        await repo.update_settings(999)

        conn.execute.assert_not_called()

    async def test_updates_only_provided_fields(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = BirthdayRepository(pool)

        await repo.update_settings(999, enabled=False)

        conn.execute.assert_called_once()
        query = conn.execute.call_args[0][0]
        assert "enabled" in query
        assert "channel_id" not in query

    async def test_invalidates_caches_when_fields_updated(self):
        _settings_cache.set("settings:999", _SETTINGS_ROW)
        pool, _ = _make_pool(execute="UPDATE 1")
        repo = BirthdayRepository(pool)

        await repo.update_settings(999, enabled=True)

        from shared.cache import _MISSING

        assert _settings_cache.get("settings:999") is _MISSING


# ---------------------------------------------------------------------------
# Query operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestListTodaysBirthdays:
    async def test_returns_empty_list_when_none(self):
        pool, _ = _make_pool(fetch=[])
        repo = BirthdayRepository(pool)

        result = await repo.list_todays_birthdays(999, 6, 15)

        assert result == []

    async def test_returns_user_year_tuples(self):
        pool, _ = _make_pool(fetch=[{"user_id": 1001, "year": 1995}])
        repo = BirthdayRepository(pool)

        result = await repo.list_todays_birthdays(999, 6, 15)

        assert result == [(1001, 1995)]


@pytest.mark.asyncio
class TestListEnabledSettings:
    async def test_returns_empty_list(self):
        _clear_caches()
        pool, _ = _make_pool(fetch=[])
        repo = BirthdayRepository(pool)

        result = await repo.list_enabled_settings()

        assert result == []

    async def test_returns_mapped_settings(self):
        _clear_caches()
        pool, _ = _make_pool(fetch=[_SETTINGS_ROW])
        repo = BirthdayRepository(pool)

        result = await repo.list_enabled_settings()

        assert len(result) == 1
        assert result[0].guild_id == 999

    async def test_result_is_cached(self):
        _clear_caches()
        pool, conn = _make_pool(fetch=[_SETTINGS_ROW])
        repo = BirthdayRepository(pool)

        await repo.list_enabled_settings()
        await repo.list_enabled_settings()

        assert conn.fetch.call_count == 1
