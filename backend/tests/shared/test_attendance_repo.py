"""Tests for atomic daily check-in persistence."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.models.attendance import CheckinStatus
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


@pytest.mark.asyncio
class TestRecordCheckin:
    async def test_success_writes_checkin_and_event_in_one_transaction(self):
        pool, conn = _pool()
        conn.fetchrow.side_effect = [_checkin_row(), {"id": 90}]
        conn.fetchval.return_value = 1
        repo = AttendanceRepository(pool)

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
        assert result.event_id == 90
        conn.transaction.assert_called_once_with()
        event_call = conn.fetchrow.await_args_list[1]
        assert "INSERT INTO community_overlay_events" in event_call.args[0]
        assert event_call.args[1:6] == ("ch1", "checkin.recorded", 1, "twitch", "u1")
        assert event_call.args[7]["total_days"] == 1
        assert event_call.args[7]["checkin_date"] == "2026-08-30"
        assert event_call.args[10] == "checkin:7"

    async def test_duplicate_returns_existing_count_without_new_event(self):
        pool, conn = _pool()
        conn.fetchrow.side_effect = [None, _checkin_row()]
        conn.fetchval.return_value = 4
        repo = AttendanceRepository(pool)

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
        assert result.event_id is None
        assert conn.fetchrow.await_count == 2
        assert all(
            "community_overlay_events" not in call.args[0] for call in conn.fetchrow.await_args_list
        )

    async def test_duplicate_lookup_and_count_are_tenant_scoped(self):
        pool, conn = _pool()
        conn.fetchrow.side_effect = [None, _checkin_row()]
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

        duplicate_sql = conn.fetchrow.await_args_list[1].args[0]
        count_sql = conn.fetchval.await_args.args[0]
        assert "channel_id = $1" in duplicate_sql
        assert "user_id = $2" in duplicate_sql
        assert "checkin_date = $3" in duplicate_sql
        assert "channel_id = $1" in count_sql
        assert "user_id = $2" in count_sql

    async def test_event_failure_propagates_from_transaction(self):
        pool, conn = _pool()
        conn.fetchrow.side_effect = [_checkin_row(), RuntimeError("event write failed")]
        conn.fetchval.return_value = 1
        repo = AttendanceRepository(pool)

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
            "created_at": _NOW,
            "updated_at": _NOW,
        }
        repo = AttendanceRepository(pool)

        settings = await repo.update_settings(
            channel_id="ch1",
            timezone="Asia/Tokyo",
            success_template="$(user) checked in $(count)",
            duplicate_template="$(user) already checked in",
        )

        assert settings.channel_id == "ch1"
        sql, *args = conn.fetchrow.await_args.args
        assert "INSERT INTO checkin_settings" in sql
        assert "ON CONFLICT (channel_id)" in sql
        assert "RETURNING" in sql
        assert args == [
            "ch1",
            "Asia/Tokyo",
            "$(user) checked in $(count)",
            "$(user) already checked in",
        ]
