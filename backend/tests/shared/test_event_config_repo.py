"""Unit tests for shared.repositories.event_config — EventConfigRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.repositories.event_config import (
    DEFAULT_TEMPLATES,
    EVENT_TYPES,
    EventConfigRepository,
    _config_cache,
    _config_list_cache,
    _seeded_events,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

_EVENT_ROW = {
    "id": 1,
    "channel_id": "ch123",
    "event_type": "follow",
    "message_template": "Thanks for the follow!",
    "enabled": True,
    "options": {},
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
    _config_cache.clear()
    _config_cache._stale.clear()
    _config_list_cache.clear()
    _config_list_cache._stale.clear()
    _seeded_events.clear()


# ---------------------------------------------------------------------------
# get_config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetConfig:
    async def test_returns_none_when_not_found(self):
        _clear_caches()
        pool, conn = _make_pool()
        conn.fetchrow.return_value = None
        repo = EventConfigRepository(pool)

        result = await repo.get_config("ch123", "follow")

        assert result is None

    async def test_returns_event_config_when_found(self):
        _clear_caches()
        pool, _ = _make_pool(fetchrow=_EVENT_ROW)
        repo = EventConfigRepository(pool)

        result = await repo.get_config("ch123", "follow")

        assert result is not None
        assert result.channel_id == "ch123"
        assert result.event_type == "follow"
        assert result.message_template == "Thanks for the follow!"
        assert result.enabled is True
        assert result.options == {}

    async def test_result_is_cached(self):
        _clear_caches()
        pool, conn = _make_pool(fetchrow=_EVENT_ROW)
        repo = EventConfigRepository(pool)

        await repo.get_config("ch123", "follow")
        await repo.get_config("ch123", "follow")

        assert conn.fetchrow.call_count == 1

    async def test_parses_options_json_string(self):
        """_row_to_config must handle options stored as a JSON string."""
        _clear_caches()
        row_with_json = {**_EVENT_ROW, "event_type": "raid", "options": '{"auto_shoutout": true}'}
        pool, _ = _make_pool(fetchrow=row_with_json)
        repo = EventConfigRepository(pool)

        result = await repo.get_config("ch123", "raid")

        assert result is not None
        assert result.options == {"auto_shoutout": True}

    async def test_different_event_types_cached_separately(self):
        _clear_caches()
        pool, conn = _make_pool(fetchrow=_EVENT_ROW)
        repo = EventConfigRepository(pool)

        await repo.get_config("ch123", "follow")
        await repo.get_config("ch123", "subscribe")

        assert conn.fetchrow.call_count == 2


# ---------------------------------------------------------------------------
# list_configs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestListConfigs:
    async def test_returns_empty_list_when_none(self):
        _clear_caches()
        pool, _ = _make_pool(fetch=[])
        repo = EventConfigRepository(pool)

        result = await repo.list_configs("ch123")

        assert result == []

    async def test_returns_mapped_configs(self):
        _clear_caches()
        rows = [
            _EVENT_ROW,
            {**_EVENT_ROW, "id": 2, "event_type": "subscribe"},
        ]
        pool, _ = _make_pool(fetch=rows)
        repo = EventConfigRepository(pool)

        result = await repo.list_configs("ch123")

        assert len(result) == 2
        types = {c.event_type for c in result}
        assert types == {"follow", "subscribe"}

    async def test_result_is_cached(self):
        _clear_caches()
        pool, conn = _make_pool(fetch=[_EVENT_ROW])
        repo = EventConfigRepository(pool)

        await repo.list_configs("ch123")
        await repo.list_configs("ch123")

        assert conn.fetch.call_count == 1


# ---------------------------------------------------------------------------
# upsert_config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUpsertConfig:
    async def test_returns_mapped_event_config(self):
        _clear_caches()
        pool, _ = _make_pool(fetchrow=_EVENT_ROW)
        repo = EventConfigRepository(pool)

        result = await repo.upsert_config("ch123", "follow", "Thanks!", True)

        assert result.event_type == "follow"
        assert result.channel_id == "ch123"

    async def test_serializes_options_to_json(self):
        pool, conn = _make_pool(fetchrow=_EVENT_ROW)
        repo = EventConfigRepository(pool)

        await repo.upsert_config("ch123", "raid", "msg", True, options={"auto_shoutout": True})

        args = conn.fetchrow.call_args[0]
        # opts_json should be a string containing the JSON
        json_arg = next(a for a in args if isinstance(a, str) and "auto_shoutout" in a)
        assert '"auto_shoutout": true' in json_arg

    async def test_invalidates_both_caches(self):
        _config_cache.set("event_config:ch123:follow", _EVENT_ROW)
        _config_list_cache.set("event_list:ch123", [_EVENT_ROW])
        pool, _ = _make_pool(fetchrow=_EVENT_ROW)
        repo = EventConfigRepository(pool)

        await repo.upsert_config("ch123", "follow", "msg", True)

        from shared.cache import _MISSING

        assert _config_cache.get("event_config:ch123:follow") is _MISSING
        assert _config_list_cache.get("event_list:ch123") is _MISSING


# ---------------------------------------------------------------------------
# ensure_defaults
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEnsureDefaults:
    async def test_inserts_defaults_on_first_call(self):
        _clear_caches()
        pool, conn = _make_pool(execute="INSERT 0 1", fetch=[_EVENT_ROW])
        repo = EventConfigRepository(pool)

        result = await repo.ensure_defaults("new_channel")

        # Should have called execute for each default event type (4 types: follow, subscribe, raid, bits)
        assert conn.execute.call_count == len(DEFAULT_TEMPLATES)
        assert isinstance(result, list)

    async def test_skips_db_insert_on_second_call(self):
        _clear_caches()
        pool, conn = _make_pool(execute="INSERT 0 1", fetch=[_EVENT_ROW])
        repo = EventConfigRepository(pool)

        await repo.ensure_defaults("ch123")
        conn.execute.reset_mock()
        conn.fetch.reset_mock()

        await repo.ensure_defaults("ch123")

        # Second call: no inserts, but list_configs is still called
        assert conn.execute.call_count == 0

    async def test_marks_channel_as_seeded(self):
        _clear_caches()
        pool, _ = _make_pool(execute="INSERT 0 1", fetch=[])
        repo = EventConfigRepository(pool)

        await repo.ensure_defaults("ch_new")

        assert "ch_new" in _seeded_events


# ---------------------------------------------------------------------------
# invalidate_channel
# ---------------------------------------------------------------------------


class TestInvalidateChannel:
    def setup_method(self):
        _clear_caches()

    def test_removes_all_event_type_keys_for_channel(self):
        from shared.cache import _MISSING

        for et in EVENT_TYPES:
            _config_cache.set(f"event_config:ch1:{et}", {"event_type": et})
        _config_list_cache.set("event_list:ch1", [])

        repo = EventConfigRepository(MagicMock())
        repo.invalidate_channel("ch1")

        for et in EVENT_TYPES:
            assert _config_cache.get(f"event_config:ch1:{et}") is _MISSING
        assert _config_list_cache.get("event_list:ch1") is _MISSING

    def test_does_not_remove_other_channel_keys(self):
        _config_cache.set("event_config:ch2:follow", {"event_type": "follow"})
        _config_list_cache.set("event_list:ch2", [])

        repo = EventConfigRepository(MagicMock())
        repo.invalidate_channel("ch1")  # invalidate ch1, not ch2

        assert _config_cache.get("event_config:ch2:follow") == {"event_type": "follow"}
        assert _config_list_cache.get("event_list:ch2") == []
