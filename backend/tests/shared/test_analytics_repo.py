"""Unit tests for shared.repositories.analytics — all three mixins via AnalyticsRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.repositories.analytics import AnalyticsRepository
from shared.repositories.analytics._caches import (
    _session_cache,
    _summary_cache,
    _top_chatters_cache,
    _top_commands_cache,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
_LATER = datetime(2024, 6, 1, 14, 0, 0, tzinfo=UTC)

_UNSET = object()  # sentinel to distinguish "not provided" from explicit None


def _make_pool(
    *,
    fetch=_UNSET,
    fetchrow=_UNSET,
    fetchval=_UNSET,
    execute=_UNSET,
    executemany=_UNSET,
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
    if executemany is not _UNSET:
        conn.executemany.return_value = executemany

    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def _clear_all_caches() -> None:
    """Clear both fresh and stale data from all analytics caches."""
    for cache in (_session_cache, _summary_cache, _top_commands_cache, _top_chatters_cache):
        cache.clear()
        cache._stale.clear()


# ---------------------------------------------------------------------------
# Session mixin — create_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCreateSession:
    async def test_returns_session_id(self):
        _clear_all_caches()
        pool, _ = _make_pool(fetchval=7)
        repo = AnalyticsRepository(pool)

        result = await repo.create_session("ch123", _NOW)

        assert result == 7

    async def test_raises_when_no_id_returned(self):
        _clear_all_caches()
        pool, _ = _make_pool(fetchval=None)
        repo = AnalyticsRepository(pool)

        with pytest.raises(ValueError, match="Failed to create session"):
            await repo.create_session("ch123", _NOW)

    async def test_passes_all_fields_to_db(self):
        _clear_all_caches()
        pool, conn = _make_pool(fetchval=1)
        repo = AnalyticsRepository(pool)

        await repo.create_session("ch123", _NOW, title="My Stream", game_name="Chess", game_id="g1")

        conn.fetchval.assert_called_once()
        args = conn.fetchval.call_args[0]
        assert "ch123" in args
        assert _NOW in args
        assert "My Stream" in args
        assert "Chess" in args
        assert "g1" in args

    async def test_invalidates_active_session_cache(self):
        _clear_all_caches()
        _session_cache.set("active:ch123", {"id": 5})
        pool, _ = _make_pool(fetchval=6)
        repo = AnalyticsRepository(pool)

        await repo.create_session("ch123", _NOW)

        from shared.cache import _MISSING

        assert _session_cache.get("active:ch123") is _MISSING


# ---------------------------------------------------------------------------
# Session mixin — get_active_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetActiveSession:
    async def test_returns_none_when_no_active_session(self):
        _clear_all_caches()
        pool, _ = _make_pool(fetchrow=None)
        repo = AnalyticsRepository(pool)

        result = await repo.get_active_session("ch123")

        assert result is None

    async def test_returns_dict_when_session_found(self):
        _clear_all_caches()
        row = {
            "id": 10,
            "channel_id": "ch123",
            "started_at": _NOW,
            "ended_at": None,
            "title": "Gaming",
            "game_name": "Chess",
        }
        pool, _ = _make_pool(fetchrow=row)
        repo = AnalyticsRepository(pool)

        result = await repo.get_active_session("ch123")

        assert result is not None
        assert result["id"] == 10
        assert result["channel_id"] == "ch123"
        assert result["title"] == "Gaming"

    async def test_result_is_cached(self):
        _clear_all_caches()
        row = {
            "id": 10,
            "channel_id": "ch123",
            "started_at": _NOW,
            "ended_at": None,
            "title": None,
            "game_name": None,
        }
        pool, conn = _make_pool(fetchrow=row)
        repo = AnalyticsRepository(pool)

        await repo.get_active_session("ch123")
        await repo.get_active_session("ch123")

        assert conn.fetchrow.call_count == 1


# ---------------------------------------------------------------------------
# Session mixin — end_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEndSession:
    async def test_calls_update_with_correct_args(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = AnalyticsRepository(pool)

        await repo.end_session(10, _LATER)

        conn.execute.assert_called_once()
        args = conn.execute.call_args[0]
        assert _LATER in args
        assert 10 in args

    async def test_clears_session_cache(self):
        _session_cache.set("active:ch123", {"id": 10})
        pool, _ = _make_pool(execute="UPDATE 1")
        repo = AnalyticsRepository(pool)

        await repo.end_session(10, _LATER)

        from shared.cache import _MISSING

        assert _session_cache.get("active:ch123") is _MISSING


# ---------------------------------------------------------------------------
# Session mixin — close_stale_sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCloseStateSessions:
    async def test_returns_count_from_execute_result(self):
        pool, _ = _make_pool(execute="UPDATE 3")
        repo = AnalyticsRepository(pool)

        result = await repo.close_stale_sessions(max_hours=12)

        assert result == 3

    async def test_returns_zero_on_no_rows_updated(self):
        pool, _ = _make_pool(execute="UPDATE 0")
        repo = AnalyticsRepository(pool)

        result = await repo.close_stale_sessions()

        assert result == 0

    async def test_clears_session_cache(self):
        _session_cache.set("active:ch123", {"id": 1})
        pool, _ = _make_pool(execute="UPDATE 0")
        repo = AnalyticsRepository(pool)

        await repo.close_stale_sessions()

        from shared.cache import _MISSING

        assert _session_cache.get("active:ch123") is _MISSING


# ---------------------------------------------------------------------------
# Session mixin — sync_session_from_vod
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSyncSessionFromVod:
    async def test_returns_none_when_session_already_exists(self):
        _clear_all_caches()
        pool, conn = _make_pool()
        conn.fetchrow.return_value = {"id": 5}
        repo = AnalyticsRepository(pool)

        result = await repo.sync_session_from_vod("ch123", _NOW, _LATER)

        assert result is None

    async def test_returns_session_id_when_created(self):
        _clear_all_caches()
        pool, conn = _make_pool()
        conn.fetchrow.return_value = None  # no existing session
        conn.fetchval.return_value = 42
        repo = AnalyticsRepository(pool)

        result = await repo.sync_session_from_vod("ch123", _NOW, _LATER)

        assert result == 42


# ---------------------------------------------------------------------------
# Session mixin — get_latest_session_time
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetLatestSessionTime:
    async def test_returns_none_when_no_sessions(self):
        _clear_all_caches()
        pool, conn = _make_pool()
        conn.fetchrow.return_value = None  # explicit None via conn directly
        repo = AnalyticsRepository(pool)

        result = await repo.get_latest_session_time("ch123")

        assert result is None

    async def test_returns_started_at_when_found(self):
        _clear_all_caches()
        pool, _ = _make_pool(fetchrow={"started_at": _NOW})
        repo = AnalyticsRepository(pool)

        result = await repo.get_latest_session_time("ch123")

        assert result == _NOW


# ---------------------------------------------------------------------------
# Events mixin — record_command_usage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRecordCommandUsage:
    async def test_calls_execute_with_session_channel_command(self):
        pool, conn = _make_pool(execute="INSERT 0 1")
        repo = AnalyticsRepository(pool)

        await repo.record_command_usage(1, "ch123", "!uptime")

        conn.execute.assert_called_once()
        args = conn.execute.call_args[0]
        assert 1 in args
        assert "ch123" in args
        assert "!uptime" in args


# ---------------------------------------------------------------------------
# Events mixin — record_follow_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRecordFollowEvent:
    async def test_calls_execute_with_all_fields(self):
        pool, conn = _make_pool(execute="INSERT 0 1")
        repo = AnalyticsRepository(pool)

        await repo.record_follow_event(1, "ch123", "u1", "user1", "User One", _NOW)

        conn.execute.assert_called_once()
        args = conn.execute.call_args[0]
        assert 1 in args
        assert "ch123" in args
        assert "u1" in args
        assert "user1" in args
        assert "User One" in args
        assert _NOW in args


# ---------------------------------------------------------------------------
# Events mixin — record_subscribe_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRecordSubscribeEvent:
    async def test_includes_metadata_with_tier_and_is_gift(self):
        pool, conn = _make_pool(execute="INSERT 0 1")
        repo = AnalyticsRepository(pool)

        await repo.record_subscribe_event(
            1, "ch123", "u1", "user1", "User One", "1000", False, _NOW
        )

        conn.execute.assert_called_once()
        args = conn.execute.call_args[0]
        # metadata dict should be passed
        metadata_arg = next(a for a in args if isinstance(a, dict))
        assert metadata_arg == {"tier": "1000", "is_gift": False}


# ---------------------------------------------------------------------------
# Events mixin — record_raid_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRecordRaidEvent:
    async def test_includes_viewers_and_broadcaster_in_metadata(self):
        pool, conn = _make_pool(execute="INSERT 0 1")
        repo = AnalyticsRepository(pool)

        await repo.record_raid_event(1, "ch123", "raider_id", "raider", 150, _NOW)

        conn.execute.assert_called_once()
        args = conn.execute.call_args[0]
        metadata_arg = next(a for a in args if isinstance(a, dict))
        assert metadata_arg["viewers"] == 150
        assert metadata_arg["from_broadcaster_id"] == "raider_id"
        assert metadata_arg["from_broadcaster_name"] == "raider"


# ---------------------------------------------------------------------------
# Events mixin — flush_chatter_stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFlushChatterStats:
    async def test_does_nothing_when_chatters_empty(self):
        pool, conn = _make_pool()
        repo = AnalyticsRepository(pool)

        await repo.flush_chatter_stats(1, "ch123", {})

        conn.executemany.assert_not_called()

    async def test_calls_executemany_with_all_chatters(self):
        pool, conn = _make_pool(executemany=None)
        repo = AnalyticsRepository(pool)

        chatters = {
            "u1": {"username": "alice", "count": 5, "last_at": _NOW},
            "u2": {"username": "bob", "count": 3, "last_at": _NOW},
        }
        await repo.flush_chatter_stats(10, "ch123", chatters)

        conn.executemany.assert_called_once()
        _, rows = conn.executemany.call_args[0]
        assert len(rows) == 2
        user_ids = {row[2] for row in rows}
        assert user_ids == {"u1", "u2"}

    async def test_rows_include_session_and_channel(self):
        pool, conn = _make_pool(executemany=None)
        repo = AnalyticsRepository(pool)

        chatters = {"u1": {"username": "alice", "count": 10, "last_at": _NOW}}
        await repo.flush_chatter_stats(99, "ch_x", chatters)

        _, rows = conn.executemany.call_args[0]
        row = rows[0]
        assert row[0] == 99  # session_id
        assert row[1] == "ch_x"  # channel_id
        assert row[2] == "u1"  # user_id
        assert row[3] == "alice"  # username
        assert row[4] is None  # display_name (optional, not provided in test data)
        assert row[5] == 10  # count
        assert row[6] == _NOW  # last_at


# ---------------------------------------------------------------------------
# Query mixin — get_session_commands
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetSessionCommands:
    async def test_returns_none_when_session_belongs_to_different_channel(self):
        pool, conn = _make_pool()
        conn.fetchrow.return_value = {"channel_id": "other_channel"}
        repo = AnalyticsRepository(pool)

        result = await repo.get_session_commands(1, "ch123")

        assert result is None

    async def test_returns_none_when_session_not_found(self):
        pool, conn = _make_pool()
        conn.fetchrow.return_value = None
        repo = AnalyticsRepository(pool)

        result = await repo.get_session_commands(99, "ch123")

        assert result is None

    async def test_returns_command_list_for_correct_channel(self):
        pool, conn = _make_pool()
        conn.fetchrow.return_value = {"channel_id": "ch123"}
        conn.fetch.return_value = [
            {"command_name": "!uptime", "usage_count": 5, "last_used_at": _NOW},
        ]
        repo = AnalyticsRepository(pool)

        result = await repo.get_session_commands(1, "ch123")

        assert result is not None
        assert len(result) == 1
        assert result[0]["command_name"] == "!uptime"
        assert result[0]["usage_count"] == 5


# ---------------------------------------------------------------------------
# Query mixin — get_session_events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetSessionEvents:
    async def test_returns_none_when_session_not_owned_by_channel(self):
        pool, conn = _make_pool()
        conn.fetchrow.return_value = {"channel_id": "other"}
        repo = AnalyticsRepository(pool)

        result = await repo.get_session_events(1, "ch123")

        assert result is None

    async def test_returns_event_list_for_correct_channel(self):
        pool, conn = _make_pool()
        conn.fetchrow.return_value = {"channel_id": "ch123"}
        conn.fetch.return_value = [
            {
                "event_type": "follow",
                "user_id": "u1",
                "username": "alice",
                "display_name": "Alice",
                "metadata": None,
                "occurred_at": _NOW,
            }
        ]
        repo = AnalyticsRepository(pool)

        result = await repo.get_session_events(1, "ch123")

        assert result is not None
        assert len(result) == 1
        assert result[0]["event_type"] == "follow"
        assert result[0]["username"] == "alice"


# ---------------------------------------------------------------------------
# Query mixin — list_top_commands
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestListTopCommands:
    async def test_returns_empty_list_when_no_commands(self):
        _clear_all_caches()
        pool, _ = _make_pool(fetch=[])
        repo = AnalyticsRepository(pool)

        result = await repo.list_top_commands("ch123")

        assert result == []

    async def test_returns_mapped_command_list(self):
        _clear_all_caches()
        pool, _ = _make_pool(
            fetch=[{"command_name": "!uptime", "total_usage": 10, "last_used": _NOW}]
        )
        repo = AnalyticsRepository(pool)

        result = await repo.list_top_commands("ch123")

        assert len(result) == 1
        assert result[0]["command_name"] == "!uptime"
        assert result[0]["usage_count"] == 10
        assert result[0]["last_used_at"] == _NOW

    async def test_caches_result(self):
        _clear_all_caches()
        pool, conn = _make_pool(fetch=[])
        repo = AnalyticsRepository(pool)

        await repo.list_top_commands("ch123")
        await repo.list_top_commands("ch123")

        assert conn.fetch.call_count == 1


# ---------------------------------------------------------------------------
# Query mixin — list_top_chatters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestListTopChatters:
    async def test_returns_empty_list_when_no_chatters(self):
        _clear_all_caches()
        pool, _ = _make_pool(fetch=[])
        repo = AnalyticsRepository(pool)

        result = await repo.list_top_chatters("ch123")

        assert result == []

    async def test_returns_mapped_chatter_list(self):
        _clear_all_caches()
        pool, _ = _make_pool(
            fetch=[{"username": "alice", "display_name": "Alice", "total_messages": 42}]
        )
        repo = AnalyticsRepository(pool)

        result = await repo.list_top_chatters("ch123")

        assert len(result) == 1
        assert result[0]["username"] == "alice"
        assert result[0]["display_name"] == "Alice"
        assert result[0]["message_count"] == 42

    async def test_caches_result(self):
        _clear_all_caches()
        pool, conn = _make_pool(fetch=[])
        repo = AnalyticsRepository(pool)

        await repo.list_top_chatters("ch123")
        await repo.list_top_chatters("ch123")

        assert conn.fetch.call_count == 1


# ---------------------------------------------------------------------------
# Query mixin — get_total_messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetTotalMessages:
    async def test_returns_integer_count(self):
        pool, _ = _make_pool(fetchval=1337)
        repo = AnalyticsRepository(pool)

        result = await repo.get_total_messages("ch123")

        assert result == 1337

    async def test_returns_zero_when_no_messages(self):
        pool, _ = _make_pool(fetchval=0)
        repo = AnalyticsRepository(pool)

        result = await repo.get_total_messages("ch123")

        assert result == 0
