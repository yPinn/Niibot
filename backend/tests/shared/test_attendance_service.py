"""Tests for attendance domain orchestration."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.models.attendance import (
    CheckinLeaderboardEntry,
    CheckinRank,
    CheckinResult,
    CheckinSettings,
    CheckinStatus,
)
from shared.services.attendance import AttendanceService


def _settings(timezone: str = "Asia/Taipei") -> CheckinSettings:
    return CheckinSettings(
        channel_id="ch1",
        timezone=timezone,
        success_template="$(user) $(count)",
        duplicate_template="already",
    )


def test_new_checkin_settings_default_reply_delay_is_five_seconds() -> None:
    assert _settings().reply_delay_seconds == 5


@pytest.mark.asyncio
class TestAttendanceService:
    async def test_get_leaderboard_uses_requested_channel(self):
        entries = (
            CheckinLeaderboardEntry(
                rank=1,
                user_id="u1",
                username="alice",
                display_name="Alice",
                total_days=12,
                last_checkin_date=date(2026, 8, 31),
            ),
        )
        repo = MagicMock()
        repo.list_leaderboard = AsyncMock(return_value=entries)
        service = AttendanceService(repo)

        result = await service.get_leaderboard("ch1")

        assert result is entries
        repo.list_leaderboard.assert_awaited_once_with("ch1")

    async def test_get_rank_uses_requested_channel_and_user(self):
        rank = CheckinRank(
            rank=3, total_days=5, last_checkin_date=date(2026, 8, 31), total_participants=42
        )
        repo = MagicMock()
        repo.get_checkin_rank = AsyncMock(return_value=rank)
        service = AttendanceService(repo)

        result = await service.get_rank("ch1", "u1")

        assert result is rank
        repo.get_checkin_rank.assert_awaited_once_with("ch1", "u1")

    async def test_get_rank_returns_none_when_the_viewer_has_no_checkins(self):
        repo = MagicMock()
        repo.get_checkin_rank = AsyncMock(return_value=None)
        service = AttendanceService(repo)

        result = await service.get_rank("ch1", "u_unknown")

        assert result is None

    async def test_get_settings_uses_requested_channel(self):
        repo = MagicMock()
        repo.get_or_create_settings = AsyncMock(return_value=_settings())
        service = AttendanceService(repo)

        settings = await service.get_settings("ch1")

        assert settings.channel_id == "ch1"
        repo.get_or_create_settings.assert_awaited_once_with("ch1")

    async def test_update_settings_validates_and_persists_complete_settings(self):
        current = _settings()
        updated = CheckinSettings(
            channel_id="ch1",
            timezone="Asia/Tokyo",
            success_template="$(@user) 第 $(count) 天",
            duplicate_template="$(@user) 今天已簽到",
        )
        repo = MagicMock()
        repo.get_or_create_settings = AsyncMock(return_value=current)
        repo.update_settings = AsyncMock(return_value=updated)
        service = AttendanceService(repo)

        result = await service.update_settings(
            "ch1",
            timezone="Asia/Tokyo",
            success_template="$(@user) 第 $(count) 天",
            duplicate_template="$(@user) 今天已簽到",
        )

        assert result is updated
        repo.update_settings.assert_awaited_once_with(
            channel_id="ch1",
            timezone="Asia/Tokyo",
            success_template="$(@user) 第 $(count) 天",
            duplicate_template="$(@user) 今天已簽到",
            reply_delay_seconds=5,
        )

    async def test_update_settings_updates_only_the_reply_delay(self):
        current = _settings()
        repo = MagicMock()
        repo.get_or_create_settings = AsyncMock(return_value=current)
        repo.update_settings = AsyncMock(return_value=current)
        service = AttendanceService(repo)

        await service.update_settings("ch1", reply_delay_seconds=5)

        repo.update_settings.assert_awaited_once_with(
            channel_id="ch1",
            timezone=current.timezone,
            success_template=current.success_template,
            duplicate_template=current.duplicate_template,
            reply_delay_seconds=5,
        )

    async def test_update_settings_rejects_invalid_timezone_before_write(self):
        repo = MagicMock()
        repo.get_or_create_settings = AsyncMock(return_value=_settings())
        repo.update_settings = AsyncMock()
        service = AttendanceService(repo)

        with pytest.raises(ValueError, match="Invalid check-in timezone"):
            await service.update_settings("ch1", timezone="Not/AZone")

        repo.update_settings.assert_not_awaited()

    async def test_update_settings_rejects_unknown_template_variable_before_write(self):
        repo = MagicMock()
        repo.get_or_create_settings = AsyncMock(return_value=_settings())
        repo.update_settings = AsyncMock()
        service = AttendanceService(repo)

        with pytest.raises(ValueError, match="Unsupported check-in template variable"):
            await service.update_settings("ch1", success_template="$(unknown)")

        repo.update_settings.assert_not_awaited()

    async def test_uses_channel_timezone_for_calendar_day(self):
        repo = MagicMock()
        repo.get_or_create_settings = AsyncMock(return_value=_settings())
        repo.record_checkin = AsyncMock(
            return_value=CheckinResult(
                status=CheckinStatus.RECORDED,
                channel_id="ch1",
                user_id="u1",
                username="alice",
                display_name="Alice",
                checkin_date=date(2026, 8, 31),
                total_days=1,
                checkin_id=1,
                event_id=2,
                occurred_at=datetime(2026, 8, 30, 16, 30, tzinfo=UTC),
            )
        )
        service = AttendanceService(repo)
        now = datetime(2026, 8, 30, 16, 30, tzinfo=UTC)

        await service.check_in(
            channel_id="ch1",
            user_id="u1",
            username="alice",
            display_name="Alice",
            occurred_at=now,
        )

        assert repo.record_checkin.await_args.kwargs["checkin_date"] == date(2026, 8, 31)

    async def test_rejects_naive_datetime(self):
        repo = MagicMock()
        repo.get_or_create_settings = AsyncMock(return_value=_settings())
        repo.record_checkin = AsyncMock()
        service = AttendanceService(repo)

        with pytest.raises(ValueError, match="timezone-aware"):
            await service.check_in(
                channel_id="ch1",
                user_id="u1",
                username="alice",
                display_name=None,
                occurred_at=datetime(2026, 8, 30, 10, 0),
            )

        repo.record_checkin.assert_not_awaited()

    async def test_invalid_configured_timezone_fails_closed(self):
        repo = MagicMock()
        repo.get_or_create_settings = AsyncMock(return_value=_settings("Not/AZone"))
        service = AttendanceService(repo)

        with pytest.raises(ValueError, match="Invalid check-in timezone"):
            await service.check_in(
                channel_id="ch1",
                user_id="u1",
                username="alice",
                display_name=None,
                occurred_at=datetime(2026, 8, 30, tzinfo=UTC),
            )

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (CheckinStatus.RECORDED, "@Alice 簽到成功，累積 3 天！"),
            (
                CheckinStatus.ALREADY_CHECKED_IN,
                "@Alice 今天已經簽到過了，目前累積 3 天！",
            ),
        ],
    )
    async def test_check_in_with_reply_selects_status_template(self, status, expected):
        settings = CheckinSettings(
            channel_id="ch1",
            timezone="Asia/Taipei",
            success_template="$(@user) 簽到成功，累積 $(count) 天！",
            duplicate_template="$(@user) 今天已經簽到過了，目前累積 $(count) 天！",
        )
        result = CheckinResult(
            status=status,
            channel_id="ch1",
            user_id="u1",
            username="alice",
            display_name="Alice",
            checkin_date=date(2026, 8, 31),
            total_days=3,
            checkin_id=1,
            event_id=2 if status is CheckinStatus.RECORDED else None,
            occurred_at=datetime(2026, 8, 30, 16, 30, tzinfo=UTC),
        )
        repo = MagicMock()
        repo.get_or_create_settings = AsyncMock(return_value=settings)
        repo.record_checkin = AsyncMock(return_value=result)
        service = AttendanceService(repo)

        outcome = await service.check_in_with_reply(
            channel_id="ch1",
            user_id="u1",
            username="alice",
            display_name="Alice",
            occurred_at=datetime(2026, 8, 30, 16, 30, tzinfo=UTC),
        )

        assert outcome.result is result
        assert outcome.message == expected

    async def test_check_in_with_reply_carries_the_channels_configured_delay(self):
        settings = CheckinSettings(
            channel_id="ch1",
            timezone="Asia/Taipei",
            success_template="$(@user) $(count)",
            duplicate_template="already $(count)",
            reply_delay_seconds=7,
        )
        result = CheckinResult(
            status=CheckinStatus.RECORDED,
            channel_id="ch1",
            user_id="u1",
            username="alice",
            display_name="Alice",
            checkin_date=date(2026, 8, 31),
            total_days=1,
            checkin_id=1,
            event_id=2,
            occurred_at=datetime(2026, 8, 30, 16, 30, tzinfo=UTC),
        )
        repo = MagicMock()
        repo.get_or_create_settings = AsyncMock(return_value=settings)
        repo.record_checkin = AsyncMock(return_value=result)
        service = AttendanceService(repo)

        outcome = await service.check_in_with_reply(
            channel_id="ch1",
            user_id="u1",
            username="alice",
            display_name="Alice",
            occurred_at=datetime(2026, 8, 30, 16, 30, tzinfo=UTC),
        )

        assert outcome.delay_seconds == 7

    async def test_check_in_with_reply_renders_current_streak(self):
        settings = CheckinSettings(
            channel_id="ch1",
            timezone="Asia/Taipei",
            success_template="$(user) 今天第 $(today_order) 位，連續 $(streak) 天，累積 $(count) 天",
            duplicate_template="already $(streak)",
        )
        result = CheckinResult(
            status=CheckinStatus.RECORDED,
            channel_id="ch1",
            user_id="u1",
            username="alice",
            display_name="Alice",
            checkin_date=date(2026, 8, 31),
            total_days=16,
            checkin_id=1,
            event_id=2,
            occurred_at=datetime(2026, 8, 30, 16, 30, tzinfo=UTC),
            current_streak=4,
            today_order=7,
        )
        repo = MagicMock()
        repo.get_or_create_settings = AsyncMock(return_value=settings)
        repo.record_checkin = AsyncMock(return_value=result)

        outcome = await AttendanceService(repo).check_in_with_reply(
            channel_id="ch1",
            user_id="u1",
            username="alice",
            display_name="Alice",
            occurred_at=datetime(2026, 8, 30, 16, 30, tzinfo=UTC),
        )

        assert outcome.message == "Alice 今天第 7 位，連續 4 天，累積 16 天"

    async def test_duplicate_reply_is_immediate_even_when_channel_delay_is_configured(self):
        settings = CheckinSettings(
            channel_id="ch1",
            timezone="Asia/Taipei",
            success_template="$(@user) $(count)",
            duplicate_template="already $(count)",
            reply_delay_seconds=7,
        )
        result = CheckinResult(
            status=CheckinStatus.ALREADY_CHECKED_IN,
            channel_id="ch1",
            user_id="u1",
            username="alice",
            display_name="Alice",
            checkin_date=date(2026, 8, 31),
            total_days=1,
            checkin_id=1,
            event_id=None,
            occurred_at=datetime(2026, 8, 30, 16, 30, tzinfo=UTC),
        )
        repo = MagicMock()
        repo.get_or_create_settings = AsyncMock(return_value=settings)
        repo.record_checkin = AsyncMock(return_value=result)
        service = AttendanceService(repo)

        outcome = await service.check_in_with_reply(
            channel_id="ch1",
            user_id="u1",
            username="alice",
            display_name="Alice",
            occurred_at=datetime(2026, 8, 30, 16, 30, tzinfo=UTC),
        )

        assert outcome.delay_seconds == 0

    async def test_invalid_template_fails_before_checkin_transaction(self):
        settings = CheckinSettings(
            channel_id="ch1",
            timezone="Asia/Taipei",
            success_template="$(user) $(unknown)",
            duplicate_template="already $(count)",
        )
        repo = MagicMock()
        repo.get_or_create_settings = AsyncMock(return_value=settings)
        repo.record_checkin = AsyncMock()
        service = AttendanceService(repo)

        with pytest.raises(ValueError, match="Unsupported check-in template variable"):
            await service.check_in_with_reply(
                channel_id="ch1",
                user_id="u1",
                username="alice",
                display_name="Alice",
                occurred_at=datetime(2026, 8, 30, 16, 30, tzinfo=UTC),
            )

        repo.record_checkin.assert_not_awaited()
