"""Tests for atomic daily check-in persistence."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.models.attendance import CheckinStatus
from shared.models.collection import (
    CollectionCardRevision,
    CollectionDraw,
    CollectionProgress,
    CollectionSet,
    DrawSelection,
    OwnedCollectionCard,
    RarityRevision,
)
from shared.repositories.attendance import AttendanceRepository

_NOW = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)
_DAY = date(2026, 8, 30)


def _pool() -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    transaction = MagicMock()
    transaction.return_value.__aenter__ = AsyncMock(return_value=None)
    transaction.return_value.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = transaction
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def _checkin_row() -> dict:
    return {
        "id": 7,
        "channel_id": "ch1",
        "user_id": "u1",
        "username": "alice",
        "display_name": "Alice",
        "checkin_date": _DAY,
        "session_id": 42,
        "created_at": _NOW,
    }


def _collection_draw() -> CollectionDraw:
    rarity = RarityRevision(21, "common", "普通", 10, 20)
    collection_set = CollectionSet(11, "aespa", "aespa", 9)
    card = CollectionCardRevision(
        card_id=31,
        revision_id=41,
        key="karina-01",
        number="001",
        name="星羅羅盤",
        description=None,
        collection_set=collection_set,
        rarity=rarity,
        portrait_url=None,
        square_url=None,
        backdrop_url=None,
    )
    return CollectionDraw(
        id=61,
        selection=DrawSelection(
            pool_revision_id=51,
            algorithm_version="weighted-rarity-v1",
            card=card,
            entropy=bytes(16),
            rarity_roll=0,
            rarity_weight_total=100,
            card_roll=0,
            card_bucket_size=5,
        ),
        is_new=True,
        copy_count=1,
        progress=CollectionProgress(owned_copies=1, unique_cards=1, total_cards=9),
        owned_cards=(OwnedCollectionCard(card=card, copy_count=1),),
    )


def _collection_repo(draw: CollectionDraw | None = None) -> MagicMock:
    repository = MagicMock()
    repository.draw_for_checkin = AsyncMock(return_value=draw or _collection_draw())
    return repository


@pytest.mark.asyncio
class TestRecordCheckin:
    async def test_carryover_same_day_is_duplicate_without_fake_ledger_or_draw(self):
        pool, conn = _pool()
        conn.fetchrow.return_value = {
            "carried_total_days": 15,
            "last_source_date": _DAY,
            "current_streak": 3,
            "source_daily_order": 5,
        }
        conn.fetchval.return_value = 0
        collection_repo = _collection_repo()
        repo = AttendanceRepository(pool, collection_repository=collection_repo)

        result = await repo.record_checkin(
            channel_id="ch1",
            user_id="u1",
            username="alice",
            display_name="Alice",
            checkin_date=_DAY,
            occurred_at=_NOW,
        )

        assert result.status is CheckinStatus.ALREADY_CHECKED_IN
        assert result.checkin_id is None
        assert result.total_days == 15
        assert result.current_streak == 3
        assert result.today_order == 5
        collection_repo.draw_for_checkin.assert_not_awaited()
        assert all(
            "INSERT INTO viewer_checkins" not in call.args[0]
            for call in conn.fetchrow.await_args_list
        )

    async def test_carryover_earlier_day_does_not_reuse_cutoff_daily_order(self):
        pool, conn = _pool()
        conn.fetchrow.return_value = {
            "carried_total_days": 15,
            "last_source_date": _DAY,
            "current_streak": 3,
            "source_daily_order": 5,
        }
        conn.fetchval.return_value = 0
        repo = AttendanceRepository(pool, collection_repository=_collection_repo())

        result = await repo.record_checkin(
            channel_id="ch1",
            user_id="u1",
            username="alice",
            display_name="Alice",
            checkin_date=_DAY - timedelta(days=1),
            occurred_at=_NOW - timedelta(days=1),
        )

        assert result.status is CheckinStatus.ALREADY_CHECKED_IN
        assert result.today_order == 0

    async def test_success_writes_checkin_and_event_in_one_transaction(self):
        pool, conn = _pool()
        conn.fetchrow.side_effect = [None, _checkin_row(), {"id": 90}]
        conn.fetchval.return_value = 1
        collection_repo = _collection_repo()
        repo = AttendanceRepository(pool, collection_repository=collection_repo)

        result = await repo.record_checkin(
            channel_id="ch1",
            user_id="u1",
            username="alice",
            display_name="Alice",
            checkin_date=_DAY,
            occurred_at=_NOW,
            session_id=42,
            event_expires_at=_NOW + timedelta(minutes=10),
        )

        assert result.status is CheckinStatus.RECORDED
        assert result.total_days == 1
        assert result.today_order == 1
        assert result.event_id == 90
        assert result.collection == _collection_draw()
        conn.transaction.assert_called_once_with()
        daily_lock = next(
            call
            for call in conn.execute.await_args_list
            if "checkin-daily-order:" in str(call.args)
        )
        assert "pg_advisory_xact_lock(hashtextextended($1, 0))" in daily_lock.args[0]
        assert daily_lock.args[1] == "checkin-daily-order:ch1:2026-08-30"
        daily_order_call = next(
            call for call in conn.fetchval.await_args_list if "id <= $3" in call.args[0]
        )
        assert daily_order_call.args[1:] == ("ch1", _DAY, 7)
        collection_repo.draw_for_checkin.assert_awaited_once_with(
            conn,
            channel_id="ch1",
            user_id="u1",
            checkin_id=7,
            drawn_at=_NOW,
        )
        event_call = conn.fetchrow.await_args_list[2]
        assert "INSERT INTO community_overlay_events" in event_call.args[0]
        assert event_call.args[1:6] == ("ch1", "checkin.recorded", 1, "twitch", "u1")
        assert event_call.args[7]["total_days"] == 1
        assert event_call.args[7]["checkin_date"] == "2026-08-30"
        assert event_call.args[7]["collection"]["draw_id"] == 61
        assert event_call.args[7]["collection"]["card"]["name"] == "星羅羅盤"
        assert event_call.args[10] == "checkin:7"

    async def test_duplicate_returns_existing_count_without_new_event(self):
        pool, conn = _pool()
        conn.fetchrow.side_effect = [None, None, _checkin_row()]
        conn.fetchval.return_value = 4
        collection_repo = _collection_repo()
        repo = AttendanceRepository(pool, collection_repository=collection_repo)

        result = await repo.record_checkin(
            channel_id="ch1",
            user_id="u1",
            username="alice",
            display_name="Alice",
            checkin_date=_DAY,
            occurred_at=_NOW,
        )

        assert result.status is CheckinStatus.ALREADY_CHECKED_IN
        assert result.total_days == 4
        assert result.today_order == 4
        assert result.event_id is None
        assert result.collection is None
        collection_repo.draw_for_checkin.assert_not_awaited()
        assert conn.fetchrow.await_count == 3
        assert all(
            "community_overlay_events" not in call.args[0] for call in conn.fetchrow.await_args_list
        )

    async def test_duplicate_lookup_and_count_are_tenant_scoped(self):
        pool, conn = _pool()
        conn.fetchrow.side_effect = [None, None, _checkin_row()]
        conn.fetchval.return_value = 2
        repo = AttendanceRepository(pool)

        await repo.record_checkin(
            channel_id="ch1",
            user_id="u1",
            username="alice",
            display_name=None,
            checkin_date=_DAY,
            occurred_at=_NOW,
        )

        duplicate_sql = conn.fetchrow.await_args_list[2].args[0]
        count_sql = next(
            call.args[0] for call in conn.fetchval.await_args_list if "COUNT(*)" in call.args[0]
        )
        assert "channel_id = $1" in duplicate_sql
        assert "user_id = $2" in duplicate_sql
        assert "checkin_date = $3" in duplicate_sql
        assert "channel_id = $1" in count_sql
        assert "user_id = $2" in count_sql

    async def test_event_failure_propagates_from_transaction(self):
        pool, conn = _pool()
        conn.fetchrow.side_effect = [None, _checkin_row(), RuntimeError("event write failed")]
        conn.fetchval.return_value = 1
        repo = AttendanceRepository(pool, collection_repository=_collection_repo())

        with pytest.raises(RuntimeError, match="event write failed"):
            await repo.record_checkin(
                channel_id="ch1",
                user_id="u1",
                username="alice",
                display_name=None,
                checkin_date=_DAY,
                occurred_at=_NOW,
            )

        conn.transaction.assert_called_once_with()

    async def test_draw_failure_prevents_overlay_event_and_rolls_back_with_checkin(self):
        pool, conn = _pool()
        conn.fetchrow.side_effect = [None, _checkin_row()]
        conn.fetchval.return_value = 1
        collection_repo = _collection_repo()
        collection_repo.draw_for_checkin.side_effect = RuntimeError("draw failed")
        repo = AttendanceRepository(pool, collection_repository=collection_repo)

        with pytest.raises(RuntimeError, match="draw failed"):
            await repo.record_checkin(
                channel_id="ch1",
                user_id="u1",
                username="alice",
                display_name=None,
                checkin_date=_DAY,
                occurred_at=_NOW,
            )

        assert conn.fetchrow.await_count == 2
        assert "viewer_checkins" in conn.fetchrow.await_args_list[1].args[0]
        conn.transaction.assert_called_once_with()

    async def test_rejects_session_from_another_channel(self):
        pool, conn = _pool()
        conn.fetchval.return_value = False
        repo = AttendanceRepository(pool)

        with pytest.raises(ValueError, match="does not belong"):
            await repo.record_checkin(
                channel_id="ch1",
                user_id="u1",
                username="alice",
                display_name=None,
                checkin_date=_DAY,
                occurred_at=_NOW,
                session_id=99,
            )

        session_sql = conn.fetchval.await_args.args[0]
        assert "channel_id = $2" in session_sql
        conn.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
class TestCheckinSettings:
    async def test_get_or_create_returns_channel_defaults(self):
        pool, conn = _pool()
        conn.fetchrow.return_value = {
            "channel_id": "ch1",
            "timezone": "Asia/Taipei",
            "success_template": "$(@user) 簽到成功，累積 $(count) 天！",
            "duplicate_template": "$(@user) 今天已經簽到過了！",
            "reply_delay_seconds": 0,
            "created_at": _NOW,
            "updated_at": _NOW,
        }
        repo = AttendanceRepository(pool)

        settings = await repo.get_or_create_settings("ch1")

        assert settings.channel_id == "ch1"
        assert settings.timezone == "Asia/Taipei"
        assert "ON CONFLICT" in conn.execute.await_args.args[0]
        assert "WHERE channel_id = $1" in conn.fetchrow.await_args.args[0]

    async def test_update_settings_upserts_only_the_requested_channel(self):
        pool, conn = _pool()
        conn.fetchrow.return_value = {
            "channel_id": "ch1",
            "timezone": "Asia/Tokyo",
            "success_template": "$(user) checked in $(count)",
            "duplicate_template": "$(user) already checked in",
            "reply_delay_seconds": 5,
            "created_at": _NOW,
            "updated_at": _NOW,
        }
        repo = AttendanceRepository(pool)

        settings = await repo.update_settings(
            channel_id="ch1",
            timezone="Asia/Tokyo",
            success_template="$(user) checked in $(count)",
            duplicate_template="$(user) already checked in",
            reply_delay_seconds=5,
        )

        assert settings.channel_id == "ch1"
        assert settings.reply_delay_seconds == 5
        sql, *args = conn.fetchrow.await_args.args
        assert "INSERT INTO checkin_settings" in sql
        assert "ON CONFLICT (channel_id)" in sql
        assert "RETURNING" in sql
        assert args == [
            "ch1",
            "Asia/Tokyo",
            "$(user) checked in $(count)",
            "$(user) already checked in",
            5,
        ]


@pytest.mark.asyncio
class TestCheckinLeaderboard:
    async def test_lists_tenant_scoped_viewer_totals_in_rank_order(self):
        pool, conn = _pool()
        conn.fetch.return_value = [
            {
                "rank": 1,
                "user_id": "u1",
                "username": "alice",
                "display_name": "Alice",
                "total_days": 12,
                "last_checkin_date": _DAY,
            },
            {
                "rank": 2,
                "user_id": "u2",
                "username": "bob",
                "display_name": None,
                "total_days": 8,
                "last_checkin_date": _DAY,
            },
        ]
        repo = AttendanceRepository(pool)

        leaderboard = await repo.list_leaderboard("ch1")

        assert [(entry.rank, entry.user_id, entry.total_days) for entry in leaderboard] == [
            (1, "u1", 12),
            (2, "u2", 8),
        ]
        sql, channel_id, limit = conn.fetch.await_args.args
        normalized_sql = " ".join(sql.split())
        assert "WHERE channel_id = $1" in normalized_sql
        assert "viewer_checkin_carryovers" in normalized_sql
        assert "carried_total_days" in normalized_sql
        assert "ORDER BY total_days DESC" in normalized_sql
        assert "LIMIT $2" in normalized_sql
        assert (channel_id, limit) == ("ch1", 100)


@pytest.mark.asyncio
class TestCheckinRank:
    async def test_returns_rank_using_the_same_ordering_as_the_leaderboard(self):
        pool, conn = _pool()
        conn.fetchrow.return_value = {
            "rank": 3,
            "total_days": 5,
            "last_checkin_date": _DAY,
            "total_participants": 42,
        }
        repo = AttendanceRepository(pool)

        rank = await repo.get_checkin_rank("ch1", "u1")

        assert rank is not None
        assert (rank.rank, rank.total_days, rank.total_participants) == (3, 5, 42)
        sql, channel_id, user_id = conn.fetchrow.await_args.args
        normalized_sql = " ".join(sql.split())
        assert "WHERE channel_id = $1" in normalized_sql
        assert "ORDER BY total_days DESC" in normalized_sql
        assert "WHERE user_id = $2" in normalized_sql
        assert (channel_id, user_id) == ("ch1", "u1")

    async def test_returns_none_when_the_viewer_has_no_checkins(self):
        pool, conn = _pool()
        conn.fetchrow.return_value = None
        repo = AttendanceRepository(pool)

        rank = await repo.get_checkin_rank("ch1", "u_unknown")

        assert rank is None
