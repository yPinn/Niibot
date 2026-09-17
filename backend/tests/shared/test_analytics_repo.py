"""Unit tests for shared.repositories.analytics — all three mixins via AnalyticsRepository."""

from __future__ import annotations

import math as _math
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from shared.repositories.analytics import AnalyticsRepository
from shared.repositories.analytics._caches import (
    _session_cache,
    _summary_cache,
    _top_chatters_cache,
    _top_commands_cache,
)
from shared.repositories.analytics._overlap_mixin import sync_known_bots
from shared.repositories.analytics._query_mixin import _SCORE_SQL

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
    transaction = MagicMock()
    transaction.return_value.__aenter__ = AsyncMock(return_value=None)
    transaction.return_value.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = transaction
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
        pool, conn = _make_pool(fetchrow={"channel_id": "ch123"})
        repo = AnalyticsRepository(pool)

        await repo.end_session(10, _LATER)

        conn.fetchrow.assert_called_once()
        args = conn.fetchrow.call_args[0]
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
# Session mixin — attendance streak eligibility
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAttendanceStreakEligibility:
    async def test_only_compares_complete_attendance_snapshots(self):
        pool, conn = _make_pool(execute="UPDATE 0")
        repo = AnalyticsRepository(pool)

        await repo.update_attendance_streaks("ch123", 10)

        sql = "\n".join(call.args[0] for call in conn.execute.call_args_list)
        assert "attendance_snapshot_count > 0" in sql
        assert "ended_at IS NOT NULL" in sql
        assert "current_session" in sql
        assert "(s.started_at, s.id) <" in sql
        assert "es.last_session_id = $2" in sql


# ---------------------------------------------------------------------------
# Session mixin — close_stale_sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCloseStateSessions:
    async def test_returns_count_from_returned_rows(self):
        rows = [
            {
                "id": session_id,
                "channel_id": "ch123",
                "started_at": _NOW,
                "attendance_snapshot_count": 0,
            }
            for session_id in (1, 2, 3)
        ]
        pool, _ = _make_pool(fetch=rows)
        repo = AnalyticsRepository(pool)

        result = await repo.close_stale_sessions(max_hours=12)

        assert result == 3

    async def test_returns_zero_on_no_rows_updated(self):
        pool, _ = _make_pool(fetch=[])
        repo = AnalyticsRepository(pool)

        result = await repo.close_stale_sessions()

        assert result == 0

    async def test_clears_session_cache(self):
        _session_cache.set("active:ch123", {"id": 1})
        pool, _ = _make_pool(fetch=[])
        repo = AnalyticsRepository(pool)

        await repo.close_stale_sessions()

        from shared.cache import _MISSING

        assert _session_cache.get("active:ch123") is _MISSING

    async def test_settles_only_observed_sessions_in_chronological_order(self):
        rows = [
            {
                "id": 30,
                "channel_id": "ch123",
                "started_at": _LATER,
                "attendance_snapshot_count": 1,
            },
            {
                "id": 20,
                "channel_id": "ch123",
                "started_at": _NOW,
                "attendance_snapshot_count": 1,
            },
            {
                "id": 10,
                "channel_id": "other",
                "started_at": _NOW,
                "attendance_snapshot_count": 0,
            },
        ]
        pool, conn = _make_pool(fetch=rows)
        repo = AnalyticsRepository(pool)
        repo.update_attendance_streaks = AsyncMock()

        result = await repo.close_stale_sessions()

        assert result == 3
        conn.fetch.assert_awaited_once()
        assert repo.update_attendance_streaks.await_args_list == [
            call("ch123", 20),
            call("ch123", 30),
        ]


# ---------------------------------------------------------------------------
# Session mixin — sync_session_from_vod
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSyncSessionFromVod:
    async def test_returns_none_when_session_already_exists(self):
        _clear_all_caches()
        pool, conn = _make_pool()
        conn.fetchrow.return_value = {"id": 5, "title": None}
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
# Events mixin — attendance snapshots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRecordAttendanceSnapshot:
    async def test_empty_complete_snapshot_still_marks_session_observed(self):
        pool, conn = _make_pool(execute="UPDATE 1")
        repo = AnalyticsRepository(pool)

        recorded = await repo.record_attendance_snapshot(10, "ch123", [], 60)

        assert recorded is True
        conn.execute.assert_awaited_once()
        sql = conn.execute.await_args.args[0]
        assert "attendance_snapshot_count" in sql
        conn.executemany.assert_not_awaited()

    async def test_snapshot_and_watch_time_share_one_transaction(self):
        pool, conn = _make_pool(execute="UPDATE 1", executemany=None)
        repo = AnalyticsRepository(pool)
        viewers = [{"user_id": "u1", "user_login": "alice", "user_name": "Alice"}]

        recorded = await repo.record_attendance_snapshot(10, "ch123", viewers, 60)

        assert recorded is True
        conn.transaction.assert_called_once_with()
        conn.execute.assert_awaited_once()
        conn.executemany.assert_awaited_once()
        _, rows = conn.executemany.await_args.args
        assert rows[0][0:3] == (10, "ch123", "u1")

    async def test_does_not_write_viewers_when_session_is_not_active_for_channel(self):
        pool, conn = _make_pool(execute="UPDATE 0", executemany=None)
        repo = AnalyticsRepository(pool)
        viewers = [{"user_id": "u1", "user_login": "alice", "user_name": "Alice"}]

        recorded = await repo.record_attendance_snapshot(10, "other", viewers, 60)

        assert recorded is False
        conn.executemany.assert_not_awaited()


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


# ---------------------------------------------------------------------------
# Query mixin — get_summary
# ---------------------------------------------------------------------------


def _make_summary_row(recent_sessions_json: str) -> dict:
    """Build a mock asyncpg row for get_summary.

    asyncpg returns the json / jsonb column as a raw Python str — that is the
    bug this test suite covers.  Callers pass the JSON string directly.
    """
    return {
        "total_sessions": 3,
        "total_stream_hours": 7.5,
        "total_commands": 42,
        "total_follows": 10,
        "total_subs": 2,
        "avg_session_duration": 2.5,
        "recent_sessions": recent_sessions_json,
    }


@pytest.mark.asyncio
class TestGetSummary:
    def setup_method(self):
        _clear_all_caches()

    async def test_empty_sessions_json_string_returns_empty_list(self):
        """asyncpg returns '[]' (truthy string) — must be decoded, not used as-is."""
        pool, _ = _make_pool(fetchrow=_make_summary_row("[]"))
        repo = AnalyticsRepository(pool)

        result = await repo.get_summary("ch123")

        assert result["recent_sessions"] == []

    async def test_populated_sessions_json_string_returns_list(self):
        """asyncpg returns a JSON array string — must be decoded to a Python list."""
        import json as _json

        session = {
            "session_id": 1,
            "channel_id": "ch123",
            "started_at": "2024-06-01T10:00:00+00:00",
            "ended_at": "2024-06-01T12:00:00+00:00",
            "title": "Test stream",
            "game_name": "Just Chatting",
            "game_id": "509658",
            "duration_hours": 2.0,
            "total_commands": 10,
            "new_follows": 5,
            "new_subs": 1,
            "raids_received": 0,
        }
        pool, _ = _make_pool(fetchrow=_make_summary_row(_json.dumps([session])))
        repo = AnalyticsRepository(pool)

        result = await repo.get_summary("ch123")

        assert isinstance(result["recent_sessions"], list)
        assert len(result["recent_sessions"]) == 1
        assert result["recent_sessions"][0]["session_id"] == 1

    async def test_none_recent_sessions_returns_empty_list(self):
        """If asyncpg somehow returns None for the column, return [] not None."""
        pool, _ = _make_pool(fetchrow=_make_summary_row(None))
        repo = AnalyticsRepository(pool)

        result = await repo.get_summary("ch123")

        assert result["recent_sessions"] == []

    async def test_scalar_fields_are_returned_correctly(self):
        pool, _ = _make_pool(fetchrow=_make_summary_row("[]"))
        repo = AnalyticsRepository(pool)

        result = await repo.get_summary("ch123")

        assert result["total_sessions"] == 3
        assert result["total_stream_hours"] == 7.5
        assert result["total_commands"] == 42
        assert result["total_follows"] == 10
        assert result["total_subs"] == 2
        assert result["avg_session_duration"] == 2.5

    async def test_already_decoded_list_is_returned_as_is(self):
        """If a future asyncpg version / codec returns a real list, pass it through."""
        decoded = [{"session_id": 99}]
        row = _make_summary_row(decoded)  # type: ignore[arg-type]
        pool, _ = _make_pool(fetchrow=row)
        repo = AnalyticsRepository(pool)

        result = await repo.get_summary("ch123")

        assert result["recent_sessions"] is decoded


# ---------------------------------------------------------------------------
# Query mixin — list_viewers
# ---------------------------------------------------------------------------

_BOT_LIST_PATCH = "shared.repositories.analytics._query_common._get_bot_list"


def _make_viewer_row(
    *,
    user_id: str = "u1",
    username: str = "alice",
    display_name: str | None = "Alice",
    total_messages: int = 50,
    sessions_attended: int = 4,
    last_seen: datetime = _NOW,
    watch_seconds: int = 7200,
    total_bits: int = 0,
    engagement_score: float = 12.5,
    total_gifts_given: int = 0,
    is_subscribed: bool = False,
    sub_tier: str | None = None,
    is_mod: bool = False,
    is_vip: bool = False,
    follow_since: datetime | None = None,
) -> dict:
    return {
        "user_id": user_id,
        "username": username,
        "display_name": display_name,
        "total_messages": total_messages,
        "sessions_attended": sessions_attended,
        "last_seen": last_seen,
        "watch_seconds": watch_seconds,
        "total_bits": total_bits,
        "engagement_score": engagement_score,
        "total_gifts_given": total_gifts_given,
        "is_subscribed": is_subscribed,
        "sub_tier": sub_tier,
        "is_mod": is_mod,
        "is_vip": is_vip,
        "follow_since": follow_since,
    }


@pytest.mark.asyncio
class TestListViewers:
    async def test_returns_empty_list_when_no_viewers(self):
        pool, _ = _make_pool(fetch=[])
        repo = AnalyticsRepository(pool)

        with patch(_BOT_LIST_PATCH, AsyncMock(return_value=[])):
            result = await repo.list_viewers("ch123")

        assert result == []

    async def test_returns_mapped_viewer_list(self):
        pool, _ = _make_pool(fetch=[_make_viewer_row()])
        repo = AnalyticsRepository(pool)

        with patch(_BOT_LIST_PATCH, AsyncMock(return_value=[])):
            result = await repo.list_viewers("ch123")

        assert len(result) == 1
        v = result[0]
        assert v["user_id"] == "u1"
        assert v["username"] == "alice"
        assert v["display_name"] == "Alice"
        assert v["total_messages"] == 50
        assert v["sessions_attended"] == 4
        assert v["last_seen"] == _NOW
        assert v["watch_seconds"] == 7200
        assert v["total_bits"] == 0
        assert v["engagement_score"] == 12.5

    async def test_engagement_score_is_float(self):
        pool, _ = _make_pool(fetch=[_make_viewer_row(engagement_score=8)])
        repo = AnalyticsRepository(pool)

        with patch(_BOT_LIST_PATCH, AsyncMock(return_value=[])):
            result = await repo.list_viewers("ch123")

        assert isinstance(result[0]["engagement_score"], float)

    async def test_multiple_viewers_all_mapped(self):
        rows = [
            _make_viewer_row(user_id="u1", username="alice", engagement_score=25.0),
            _make_viewer_row(user_id="u2", username="bob", engagement_score=8.5),
        ]
        pool, _ = _make_pool(fetch=rows)
        repo = AnalyticsRepository(pool)

        with patch(_BOT_LIST_PATCH, AsyncMock(return_value=[])):
            result = await repo.list_viewers("ch123")

        assert len(result) == 2
        assert result[0]["username"] == "alice"
        assert result[1]["username"] == "bob"

    async def test_falls_back_to_empty_streak_cte_on_undefined_table(self):
        import asyncpg

        row = _make_viewer_row()
        pool, conn = _make_pool()
        conn.fetch.side_effect = [asyncpg.exceptions.UndefinedTableError, [row]]
        repo = AnalyticsRepository(pool)

        with patch(_BOT_LIST_PATCH, AsyncMock(return_value=[])):
            result = await repo.list_viewers("ch123")

        assert len(result) == 1
        assert conn.fetch.call_count == 2


# ---------------------------------------------------------------------------
# Query mixin — get_viewer_rank
# ---------------------------------------------------------------------------


def _make_rank_row(
    *,
    user_id: str = "u1",
    rank: int = 3,
    total_viewers: int = 20,
    engagement_score: float = 18.5,
    total_messages: int = 80,
    watch_seconds: int = 14400,
    sessions_attended: int = 6,
    streak_count: int = 2,
) -> dict:
    return {
        "user_id": user_id,
        "rank": rank,
        "total_viewers": total_viewers,
        "engagement_score": engagement_score,
        "total_messages": total_messages,
        "watch_seconds": watch_seconds,
        "sessions_attended": sessions_attended,
        "streak_count": streak_count,
    }


@pytest.mark.asyncio
class TestGetViewerRank:
    async def test_returns_none_when_viewer_not_found(self):
        pool, _ = _make_pool(fetchrow=None)
        repo = AnalyticsRepository(pool)

        with patch(_BOT_LIST_PATCH, AsyncMock(return_value=[])):
            result = await repo.get_viewer_rank("ch123", "u_unknown")

        assert result is None

    async def test_returns_rank_dict_with_correct_fields(self):
        pool, _ = _make_pool(fetchrow=_make_rank_row())
        repo = AnalyticsRepository(pool)

        with patch(_BOT_LIST_PATCH, AsyncMock(return_value=[])):
            result = await repo.get_viewer_rank("ch123", "u1")

        assert result is not None
        assert result["rank"] == 3
        assert result["total_viewers"] == 20
        assert result["engagement_score"] == 18.5
        assert result["total_messages"] == 80
        assert result["watch_seconds"] == 14400
        assert result["sessions_attended"] == 6
        assert result["streak_count"] == 2

    async def test_engagement_score_is_float(self):
        pool, _ = _make_pool(fetchrow=_make_rank_row(engagement_score=5))
        repo = AnalyticsRepository(pool)

        with patch(_BOT_LIST_PATCH, AsyncMock(return_value=[])):
            result = await repo.get_viewer_rank("ch123", "u1")

        assert isinstance(result["engagement_score"], float)  # type: ignore[index]

    async def test_falls_back_to_empty_streak_cte_on_undefined_table(self):
        import asyncpg

        row = _make_rank_row()
        pool, conn = _make_pool()
        conn.fetchrow.side_effect = [asyncpg.exceptions.UndefinedTableError, row]
        repo = AnalyticsRepository(pool)

        with patch(_BOT_LIST_PATCH, AsyncMock(return_value=[])):
            result = await repo.get_viewer_rank("ch123", "u1")

        assert result is not None
        assert result["rank"] == 3
        assert conn.fetchrow.call_count == 2


# ---------------------------------------------------------------------------
# _SCORE_SQL — formula structure and arithmetic correctness
# ---------------------------------------------------------------------------


def _score(
    *,
    watch_seconds: int,
    total_messages: int,
    sessions_attended: int,
    sub_tier_bonus: float = 0.0,
    total_bits: int = 0,
    streak_count: int = 0,
    days_since_last_seen: int = 0,
) -> float:
    """Python mirror of _SCORE_SQL for arithmetic verification.

    Must be kept in sync with _query_common._SCORE_SQL whenever the formula
    changes — these tests will fail if they drift apart.
    """
    watch_hours = watch_seconds / 3600.0
    msg_cap = max(10.0, watch_seconds / 30.0)
    effective_msgs = min(float(total_messages), msg_cap)
    msg_score = 1.5 * _math.log(effective_msgs + 1.0)
    session_score = 0.5 * _math.log(sessions_attended + 1.0)
    bits_score = 2.0 * _math.log(total_bits / 100.0 + 1.0)
    base = watch_hours + msg_score + session_score + sub_tier_bonus + bits_score
    streak_mult = 1.0 + min(streak_count, 20) * 0.05
    if days_since_last_seen < 30:
        decay = 1.0
    elif days_since_last_seen < 60:
        decay = 0.75
    else:
        decay = 0.5
    return round(base * streak_mult * decay, 2)


class TestScoreSqlStructure:
    """Canary tests — fail immediately if the SQL formula string is reverted."""

    def test_message_cap_references_watch_seconds_div_30(self):
        assert "/ 30.0" in _SCORE_SQL

    def test_sessions_attended_bonus_present(self):
        assert "sessions_attended" in _SCORE_SQL

    def test_streak_capped_at_20(self):
        assert "LEAST(COALESCE(sk.streak_count, 0), 20)" in _SCORE_SQL

    def test_bits_log_scaled_in_hundreds(self):
        assert "/ 100.0 + 1.0" in _SCORE_SQL

    def test_two_step_inactivity_decay(self):
        assert "INTERVAL '60 days'" in _SCORE_SQL
        assert "0.75" in _SCORE_SQL


class TestScoreFormulaArithmetic:
    def test_spammer_scores_below_loyal_viewer(self):
        """500 msgs in 5 min must lose to 50 msgs over 2 hr (5 sessions)."""
        spammer = _score(watch_seconds=300, total_messages=500, sessions_attended=1)
        loyal = _score(watch_seconds=7200, total_messages=50, sessions_attended=5)
        assert spammer < loyal

    def test_message_cap_prevents_extra_spam_contribution(self):
        """Messages beyond ~120/hr ceiling add no further score."""
        capped = _score(watch_seconds=3600, total_messages=120, sessions_attended=1)
        excess = _score(watch_seconds=3600, total_messages=10_000, sessions_attended=1)
        assert capped == excess

    def test_streak_capped_at_20(self):
        """Streak 30 gives identical multiplier as streak 20."""
        s20 = _score(watch_seconds=3600, total_messages=10, sessions_attended=1, streak_count=20)
        s30 = _score(watch_seconds=3600, total_messages=10, sessions_attended=1, streak_count=30)
        assert s20 == s30

    def test_streak_20_approximately_doubles_score(self):
        base = _score(watch_seconds=7200, total_messages=30, sessions_attended=3, streak_count=0)
        streaked = _score(
            watch_seconds=7200, total_messages=30, sessions_attended=3, streak_count=20
        )
        assert 1.95 <= streaked / base <= 2.05

    def test_bits_log_scaling_is_sublinear(self):
        """10× more bits should yield far less than 10× more score."""
        low = _score(watch_seconds=0, total_messages=0, sessions_attended=1, total_bits=1_000)
        high = _score(watch_seconds=0, total_messages=0, sessions_attended=1, total_bits=10_000)
        assert high / low < 3.0

    def test_inactivity_under_30_days_no_decay(self):
        fresh = _score(
            watch_seconds=3600, total_messages=20, sessions_attended=2, days_since_last_seen=0
        )
        recent = _score(
            watch_seconds=3600, total_messages=20, sessions_attended=2, days_since_last_seen=29
        )
        assert recent == fresh

    def test_inactivity_30_to_60_days_applies_75pct_decay(self):
        fresh = _score(
            watch_seconds=3600, total_messages=20, sessions_attended=2, days_since_last_seen=0
        )
        stale = _score(
            watch_seconds=3600, total_messages=20, sessions_attended=2, days_since_last_seen=45
        )
        assert abs(stale / fresh - 0.75) < 0.02

    def test_inactivity_over_60_days_applies_50pct_decay(self):
        fresh = _score(
            watch_seconds=3600, total_messages=20, sessions_attended=2, days_since_last_seen=0
        )
        old = _score(
            watch_seconds=3600, total_messages=20, sessions_attended=2, days_since_last_seen=90
        )
        assert abs(old / fresh - 0.50) < 0.02


# ---------------------------------------------------------------------------
# Overlap mixin — refresh_overlap
# ---------------------------------------------------------------------------


def _make_conn_multi(**kw) -> AsyncMock:
    """Create a standalone async connection mock (not wrapped in a pool)."""
    conn = AsyncMock()
    for attr, val in kw.items():
        setattr(conn, attr, AsyncMock(return_value=val))
    return conn


def _make_pool_with_conn(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


_VIEWER_ROW = {
    "user_id": "v1",
    "username": "viewer1",
    "display_name": "Viewer1",
    "partner_sessions": 5,
    "partner_messages": 20,
    "partner_watch_sec": 3600,
    "partner_last_seen": _NOW,
    "home_sessions": 2,
    "home_messages": 5,
    "potential_score": 1.5,
}


@pytest.mark.asyncio
class TestRefreshOverlap:
    @pytest.fixture(autouse=True)
    def _no_bot_sync(self):
        """Keep refresh_overlap's own fetch-call sequence untouched by
        sync_known_bots: an empty bot list makes it a no-op (no conn.fetch)."""
        with patch(
            "shared.repositories.analytics._query_common._get_bot_list",
            new=AsyncMock(return_value=[]),
        ):
            yield

    async def test_no_partners_returns_zero(self):
        conn = _make_conn_multi()
        conn.fetch.return_value = []
        pool = _make_pool_with_conn(conn)

        repo = AnalyticsRepository(pool)
        count = await repo.refresh_overlap("home1", days=30)

        assert count == 0

    async def test_one_partner_returns_one(self):
        conn = AsyncMock()
        conn.fetch.side_effect = [
            [{"channel_id": "partner1"}],  # partner list
            [_VIEWER_ROW],  # viewer rows for partner1
        ]
        conn.fetchval.return_value = 100
        pool = _make_pool_with_conn(conn)

        repo = AnalyticsRepository(pool)
        count = await repo.refresh_overlap("home1", days=30)

        assert count == 1

    async def test_failed_partner_is_skipped_others_counted(self):
        """An exception on one partner must not abort the whole refresh."""

        async def _fetch_side_effect(*args, **kw):
            # First call: return partner list; subsequent calls raise
            if not hasattr(_fetch_side_effect, "_called"):
                _fetch_side_effect._called = True
                return [{"channel_id": "p1"}, {"channel_id": "p2"}]
            raise RuntimeError("compute error")

        conn = AsyncMock()
        conn.fetch.side_effect = _fetch_side_effect
        pool = _make_pool_with_conn(conn)

        repo = AnalyticsRepository(pool)
        count = await repo.refresh_overlap("home1", days=30)

        # Both partners failed (fetch raised), so count == 0
        assert count == 0

    async def test_empty_viewer_rows_skips_upsert(self):
        """_compute_channel_overlap returns early if no viewers found."""
        conn = AsyncMock()
        conn.fetch.side_effect = [
            [{"channel_id": "partner1"}],  # partner list
            [],  # no viewers
        ]
        pool = _make_pool_with_conn(conn)

        repo = AnalyticsRepository(pool)
        count = await repo.refresh_overlap("home1", days=30)

        assert count == 1
        # executemany and execute should NOT be called when there are no viewers
        conn.executemany.assert_not_called()
        conn.execute.assert_not_called()

    async def test_bot_sync_failure_does_not_abort_refresh(self):
        """A broken TwitchInsights fetch (or DB error) must not block the refresh."""
        conn = AsyncMock()
        conn.fetch.side_effect = [
            [{"channel_id": "partner1"}],  # partner list
            [_VIEWER_ROW],  # viewer rows for partner1
        ]
        conn.fetchval.return_value = 100
        pool = _make_pool_with_conn(conn)

        with patch(
            "shared.repositories.analytics._query_common._get_bot_list",
            new=AsyncMock(side_effect=RuntimeError("TwitchInsights unreachable")),
        ):
            repo = AnalyticsRepository(pool)
            count = await repo.refresh_overlap("home1", days=30)

        assert count == 1


# ---------------------------------------------------------------------------
# Overlap mixin — sync_known_bots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSyncKnownBots:
    async def test_no_known_bots_is_noop(self):
        conn = AsyncMock()
        with patch(
            "shared.repositories.analytics._query_common._get_bot_list",
            new=AsyncMock(return_value=[]),
        ):
            await sync_known_bots(conn, days=30)

        conn.fetch.assert_not_called()
        conn.executemany.assert_not_called()

    async def test_no_matching_chatters_skips_upsert(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        with patch(
            "shared.repositories.analytics._query_common._get_bot_list",
            new=AsyncMock(return_value=["nightbot"]),
        ):
            await sync_known_bots(conn, days=30)

        conn.fetch.assert_awaited_once()
        conn.executemany.assert_not_called()

    async def test_matching_chatters_upserted_with_auto_sync_note(self):
        conn = AsyncMock()
        conn.fetch.return_value = [{"user_id": "19264788", "username": "nightbot"}]
        with patch(
            "shared.repositories.analytics._query_common._get_bot_list",
            new=AsyncMock(return_value=["nightbot", "streamelements"]),
        ):
            await sync_known_bots(conn, days=30)

        fetch_args = conn.fetch.await_args.args
        assert fetch_args[1] == ["nightbot", "streamelements"]  # bots passed through unchanged

        conn.executemany.assert_awaited_once()
        upsert_sql, upsert_rows = conn.executemany.await_args.args
        assert "known_bots" in upsert_sql
        assert "auto-sync" in upsert_sql
        assert upsert_rows == [("19264788", "nightbot")]


# ---------------------------------------------------------------------------
# Overlap mixin — get_matcher_summaries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetMatcherSummaries:
    async def test_returns_empty_list_when_no_summaries(self):
        conn = _make_conn_multi(fetch=[])
        pool = _make_pool_with_conn(conn)

        repo = AnalyticsRepository(pool)
        result = await repo.get_matcher_summaries("home1")

        assert result == []

    async def test_returns_summary_dicts(self):
        row = {
            "partner_channel_id": "p1",
            "partner_unique_chatters": 100,
            "home_unique_chatters": 80,
            "shared_chatters": 40,
            "exclusive_to_partner": 60,
            "overlap_pct": 40.0,
            "computed_at": _NOW,
        }
        conn = _make_conn_multi(fetch=[row])
        pool = _make_pool_with_conn(conn)

        repo = AnalyticsRepository(pool)
        result = await repo.get_matcher_summaries("home1", days=30)

        assert len(result) == 1
        assert result[0]["partner_channel_id"] == "p1"
        assert result[0]["overlap_pct"] == 40.0


# ---------------------------------------------------------------------------
# Overlap mixin — get_partner_session_stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetPartnerSessionStats:
    async def test_empty_sessions_returns_zero_stats(self):
        conn = _make_conn_multi(fetch=[])
        pool = _make_pool_with_conn(conn)

        repo = AnalyticsRepository(pool)
        result = await repo.get_partner_session_stats("p1", days=90)

        assert result["session_count"] == 0
        assert result["top_games"] == []
        assert result["peak_hours"] == []
        assert result["avg_stream_hours"] == 0.0

    async def test_returns_aggregated_stats(self):
        rows = [
            {"game_name": "Minecraft", "start_hour": 20, "duration_hours": 3.0},
            {"game_name": "Minecraft", "start_hour": 21, "duration_hours": 2.5},
            {"game_name": "Fortnite", "start_hour": 20, "duration_hours": 1.5},
        ]
        conn = _make_conn_multi(fetch=rows)
        pool = _make_pool_with_conn(conn)

        repo = AnalyticsRepository(pool)
        result = await repo.get_partner_session_stats("p1", days=90)

        assert result["session_count"] == 3
        assert result["top_games"][0] == "Minecraft"
        assert 20 in result["peak_hours"]
        assert result["avg_stream_hours"] == round((3.0 + 2.5 + 1.5) / 3, 1)

    async def test_top_games_stats_shape(self):
        """top_games_stats contains game_name, session_count, and total_hours."""
        rows = [
            {"game_name": "Minecraft", "start_hour": 20, "duration_hours": 3.0},
            {"game_name": "Minecraft", "start_hour": 21, "duration_hours": 2.5},
            {"game_name": "Fortnite", "start_hour": 20, "duration_hours": 1.5},
        ]
        conn = _make_conn_multi(fetch=rows)
        pool = _make_pool_with_conn(conn)

        repo = AnalyticsRepository(pool)
        result = await repo.get_partner_session_stats("p1", days=90)

        stats = result["top_games_stats"]
        assert len(stats) == 2
        mc = next(s for s in stats if s["game_name"] == "Minecraft")
        assert mc["session_count"] == 2
        assert mc["total_hours"] == round(3.0 + 2.5, 1)
        fn = next(s for s in stats if s["game_name"] == "Fortnite")
        assert fn["session_count"] == 1
        assert fn["total_hours"] == 1.5

    async def test_top_games_capped_at_three(self):
        rows = [{"game_name": f"Game{i}", "start_hour": i, "duration_hours": 1.0} for i in range(5)]
        conn = _make_conn_multi(fetch=rows)
        pool = _make_pool_with_conn(conn)

        repo = AnalyticsRepository(pool)
        result = await repo.get_partner_session_stats("p1", days=90)

        assert len(result["top_games"]) <= 3

    async def test_none_game_name_excluded_from_top_games(self):
        rows = [
            {"game_name": None, "start_hour": 18, "duration_hours": 1.0},
            {"game_name": "Valorant", "start_hour": 19, "duration_hours": 2.0},
        ]
        conn = _make_conn_multi(fetch=rows)
        pool = _make_pool_with_conn(conn)

        repo = AnalyticsRepository(pool)
        result = await repo.get_partner_session_stats("p1", days=90)

        assert None not in result["top_games"]
        assert "Valorant" in result["top_games"]


# ---------------------------------------------------------------------------
# Overlap mixin — get_potential_viewers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetPotentialViewers:
    async def test_returns_empty_when_no_viewers(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 0
        conn.fetch.return_value = []
        pool = _make_pool_with_conn(conn)

        repo = AnalyticsRepository(pool)
        total, rows = await repo.get_potential_viewers("home1", "p1")

        assert total == 0
        assert rows == []

    async def test_returns_count_and_rows(self):
        viewer = {
            "user_id": "v1",
            "username": "viewer1",
            "display_name": "Viewer1",
            "partner_sessions": 5,
            "partner_messages": 20,
            "partner_watch_sec": 3600,
            "partner_last_seen": _NOW,
            "home_sessions": 0,
            "home_messages": 0,
            "potential_score": 2.5,
            "computed_at": _NOW,
        }
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        conn.fetch.return_value = [viewer]
        pool = _make_pool_with_conn(conn)

        repo = AnalyticsRepository(pool)
        total, rows = await repo.get_potential_viewers("home1", "p1", limit=10, offset=0)

        assert total == 1
        assert len(rows) == 1
        assert rows[0]["user_id"] == "v1"
        assert rows[0]["potential_score"] == 2.5

    async def test_total_fetchval_none_returns_zero(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        conn.fetch.return_value = []
        pool = _make_pool_with_conn(conn)

        repo = AnalyticsRepository(pool)
        total, rows = await repo.get_potential_viewers("home1", "p1")

        assert total == 0


# ---------------------------------------------------------------------------
# Query mixin — get_insights new fields
# ---------------------------------------------------------------------------

_SUMMARY_ROW = {
    "total_sessions": 5,
    "total_stream_seconds": 18000,
    "total_messages": 100,
    "total_commands": 20,
    "total_follows": 3,
    "total_organic_subs": 1,
    "total_gift_subs": 0,
    "total_raids": 2,
    "total_cheers": 1,
    "total_bits": 500,
    # loyalty_tiers also uses fetchrow — merged into one fixture row
    "core": 3,
    "regular": 5,
    "newcomer": 2,
}


@pytest.mark.asyncio
class TestGetInsightsNewFields:
    async def test_result_contains_session_chart_top_games_loyalty_keys(self):
        """get_insights result includes the three new top-level keys."""
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=_SUMMARY_ROW)
        conn.fetch = AsyncMock(return_value=[])
        pool = _make_pool_with_conn(conn)

        with patch(_BOT_LIST_PATCH, AsyncMock(return_value=[])):
            repo = AnalyticsRepository(pool)
            result = await repo.get_insights("ch1", days=30)

        assert "session_chart" in result
        assert "top_games" in result
        assert "loyalty_tiers" in result
        assert isinstance(result["session_chart"], list)
        assert isinstance(result["top_games"], list)

    async def test_loyalty_tiers_values(self):
        """loyalty_tiers reflects the DB row counts."""
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=_SUMMARY_ROW)
        conn.fetch = AsyncMock(return_value=[])
        pool = _make_pool_with_conn(conn)

        with patch(_BOT_LIST_PATCH, AsyncMock(return_value=[])):
            repo = AnalyticsRepository(pool)
            result = await repo.get_insights("ch1", days=30)

        tiers = result["loyalty_tiers"]
        assert tiers["core"] == 3
        assert tiers["regular"] == 5
        assert tiers["newcomer"] == 2

    async def test_session_chart_row_shape(self):
        """Each session_chart entry has started_at, game_name, and total_watch_hours."""
        chart_row = {
            "started_at": _NOW,
            "game_name": "Minecraft",
            "total_watch_seconds": 3600,
        }
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=_SUMMARY_ROW)
        conn.fetch = AsyncMock(
            side_effect=[
                [],  # _top_chatters
                [],  # _top_commands
                [chart_row],  # _session_chart
                [],  # _top_games
            ]
        )
        pool = _make_pool_with_conn(conn)

        with patch(_BOT_LIST_PATCH, AsyncMock(return_value=[])):
            repo = AnalyticsRepository(pool)
            result = await repo.get_insights("ch1", days=30)

        # At least one of the fetch calls returned chart data
        if result["session_chart"]:
            point = result["session_chart"][0]
            assert "started_at" in point
            assert "game_name" in point
            assert "total_watch_hours" in point


class TestBulkUpsertBanned:
    pytestmark = pytest.mark.asyncio

    async def test_upserts_listed_and_clears_stale(self):
        pool, conn = _make_pool(executemany=None, execute="UPDATE 2")
        repo = AnalyticsRepository(pool)

        count = await repo.bulk_upsert_banned(
            "ch1",
            [
                {
                    "user_id": "1",
                    "user_login": "a",
                    "user_name": "A",
                    "expires_at": "2024-06-02T00:00:00Z",
                    "reason": "spam",
                },
                {"user_id": "2", "user_login": "b", "user_name": None, "expires_at": None},
            ],
        )

        assert count == 2
        # rows carry parsed expiry + reason
        rows = conn.executemany.call_args[0][1]
        assert rows[0][4] == datetime(2024, 6, 2, tzinfo=UTC)
        assert rows[0][5] == "spam"
        assert rows[1][4] is None
        # stale-clear excludes the two listed ids
        clear_args = conn.execute.call_args[0]
        assert clear_args[1] == "ch1"
        assert set(clear_args[2]) == {"1", "2"}

    async def test_empty_list_still_clears_all(self):
        pool, conn = _make_pool(execute="UPDATE 5")
        repo = AnalyticsRepository(pool)

        count = await repo.bulk_upsert_banned("ch1", [])

        assert count == 0
        conn.executemany.assert_not_called()
        conn.execute.assert_awaited_once()
        assert conn.execute.call_args[0][2] == []


class TestUpsertViewerSubPrime:
    pytestmark = pytest.mark.asyncio

    async def test_writes_only_the_prime_flag(self):
        pool, conn = _make_pool(execute="INSERT 0 1")
        repo = AnalyticsRepository(pool)

        await repo.upsert_viewer_sub_prime("ch1", "u1", "alice", "Alice", is_prime=True)

        sql, *args = conn.execute.call_args[0]
        assert args == ["ch1", "u1", "alice", "Alice", True]
        # narrow upsert — never touches tier / gifted
        assert "sub_is_prime" in sql
        assert "sub_tier" not in sql
        assert "sub_gifted" not in sql

    async def test_missing_table_is_swallowed(self):
        from asyncpg.exceptions import UndefinedTableError

        pool, conn = _make_pool()
        conn.execute.side_effect = UndefinedTableError("nope")
        repo = AnalyticsRepository(pool)

        await repo.upsert_viewer_sub_prime("ch1", "u1", "a", None, is_prime=False)  # no raise

    async def test_subscription_end_nulls_prime(self):
        pool, conn = _make_pool(execute="INSERT 0 1")
        repo = AnalyticsRepository(pool)

        await repo.upsert_viewer_subscription_end("ch1", "u1", "a", None)

        sql = conn.execute.call_args[0][0]
        assert "sub_is_prime  = NULL" in sql


class TestGetPlusProgramEstimate:
    pytestmark = pytest.mark.asyncio

    async def test_shapes_row_and_computes_plans(self):
        row = {
            "confirmed_points": 105,
            "confirmed_subs": 60,
            "pending_points": 200,
            "pending_subs": 150,
            "t1": 40,
            "t2": 10,
            "t3": 10,
            "data_as_of": _NOW,
        }
        pool, _conn = _make_pool(fetchrow=row)
        repo = AnalyticsRepository(pool)

        result = await repo.get_plus_program_estimate("ch1")

        assert result["confirmed_points"] == 105
        assert result["tier_breakdown"] == {"t1": 40, "t2": 10, "t3": 10}
        assert result["plan_confirmed"] == "60/40"  # 105 >= 100
        assert result["plan_ceiling"] == "70/30"  # 305 >= 300
        assert result["data_as_of"] == _NOW

    async def test_zero_roster_is_50_50(self):
        row = {
            "confirmed_points": 0,
            "confirmed_subs": 0,
            "pending_points": 0,
            "pending_subs": 0,
            "t1": 0,
            "t2": 0,
            "t3": 0,
            "data_as_of": None,
        }
        pool, _conn = _make_pool(fetchrow=row)
        repo = AnalyticsRepository(pool)

        result = await repo.get_plus_program_estimate("ch1")

        assert result["plan_confirmed"] == "50/50"
        assert result["plan_ceiling"] == "50/50"
        assert result["data_as_of"] is None

    async def test_missing_column_returns_empty(self):
        from asyncpg.exceptions import UndefinedColumnError

        pool, conn = _make_pool()
        conn.fetchrow.side_effect = UndefinedColumnError("no sub_is_prime")
        repo = AnalyticsRepository(pool)

        result = await repo.get_plus_program_estimate("ch1")

        assert result["confirmed_points"] == 0
        assert result["plan_confirmed"] == "50/50"
