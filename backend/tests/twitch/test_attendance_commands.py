"""Command-level tests for daily check-in and the development OVL trigger."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from twitch.components.attendance import AttendanceComponent

from shared.models.attendance import (
    CheckinRank,
    CheckinReply,
    CheckinResult,
    CheckinStatus,
)

PATCH_CHECK = "twitch.components.attendance.check_command"
_NOW = datetime(2026, 8, 31, 10, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _attendance_settings():
    with patch("twitch.components.attendance.get_settings") as settings:
        settings.return_value.is_development = False
        yield


def _result(status: CheckinStatus = CheckinStatus.RECORDED) -> CheckinResult:
    return CheckinResult(
        status=status,
        channel_id="ch1",
        user_id="u1",
        username="alice",
        display_name="Alice",
        checkin_date=date(2026, 8, 31),
        total_days=3,
        checkin_id=7,
        event_id=90 if status is CheckinStatus.RECORDED else None,
        occurred_at=_NOW,
    )


def _component() -> AttendanceComponent:
    bot = MagicMock()
    bot.token_database = MagicMock()
    bot.channels = MagicMock()
    bot.sessions.session_id.return_value = 42
    component = AttendanceComponent(bot)
    component.attendance = MagicMock()
    component.attendance.check_in_with_reply = AsyncMock(
        return_value=CheckinReply(result=_result(), message="@Alice 簽到成功，累積 3 天！")
    )
    component.attendance.get_rank = AsyncMock(
        return_value=CheckinRank(
            rank=8, total_days=12, last_checkin_date=date(2026, 8, 31), total_participants=132
        )
    )
    component.overlay = MagicMock()
    component.overlay.publish_checkin_preview = AsyncMock(return_value=91)
    component._ctx_reply = AsyncMock()
    component._record_command = AsyncMock()
    return component


def _ctx(*, broadcaster: bool = False) -> MagicMock:
    ctx = MagicMock()
    ctx.channel.id = "ch1"
    ctx.channel.name = "streamer"
    ctx.chatter.id = "ch1" if broadcaster else "u1"
    ctx.chatter.name = "alice"
    ctx.chatter.display_name = "Alice"
    ctx.chatter.broadcaster = broadcaster
    return ctx


async def _checkin(component: AttendanceComponent, ctx: MagicMock) -> None:
    await AttendanceComponent.checkin.callback(component, ctx)  # type: ignore[attr-defined]


async def _ovltest(component: AttendanceComponent, ctx: MagicMock, count: int = 7) -> None:
    await AttendanceComponent.ovltest.callback(component, ctx, count=count)  # type: ignore[attr-defined]


async def _rank(component: AttendanceComponent, ctx: MagicMock) -> None:
    await AttendanceComponent.rank.callback(component, ctx)  # type: ignore[attr-defined]


@pytest.mark.asyncio
class TestCheckinCommand:
    async def test_guard_denial_does_not_touch_attendance(self) -> None:
        component = _component()
        with patch(PATCH_CHECK, AsyncMock(return_value=None)):
            await _checkin(component, _ctx())

        component.attendance.check_in_with_reply.assert_not_awaited()

    async def test_records_and_replies_with_channel_scoped_result(self) -> None:
        component = _component()
        ctx = _ctx()
        with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
            await _checkin(component, ctx)

        component.attendance.check_in_with_reply.assert_awaited_once_with(
            channel_id="ch1",
            user_id="u1",
            username="alice",
            display_name="Alice",
            session_id=42,
        )
        component._ctx_reply.assert_awaited_once_with(ctx, "@Alice 簽到成功，累積 3 天！")
        component._record_command.assert_awaited_once_with(ctx, "checkin")

    async def test_duplicate_uses_duplicate_message_without_new_event(self) -> None:
        component = _component()
        component.attendance.check_in_with_reply.return_value = CheckinReply(
            result=_result(CheckinStatus.ALREADY_CHECKED_IN),
            message="@Alice 今天已經簽到過了，目前累積 3 天！",
        )
        ctx = _ctx()
        with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
            await _checkin(component, ctx)

        component._ctx_reply.assert_awaited_once_with(
            ctx, "@Alice 今天已經簽到過了，目前累積 3 天！"
        )
        component._record_command.assert_awaited_once_with(ctx, "checkin")

    async def test_database_failure_never_reports_success_or_usage(self) -> None:
        component = _component()
        component.attendance.check_in_with_reply.side_effect = RuntimeError("db unavailable")
        ctx = _ctx()
        with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
            await _checkin(component, ctx)

        component._ctx_reply.assert_awaited_once_with(ctx, "簽到失敗，請稍後再試")
        component._record_command.assert_not_awaited()

    async def test_configured_delay_sleeps_before_the_chat_reply(self) -> None:
        component = _component()
        component.attendance.check_in_with_reply.return_value = CheckinReply(
            result=_result(), message="@Alice 簽到成功，累積 3 天！", delay_seconds=5
        )
        ctx = _ctx()
        calls: list[str] = []
        sleep_mock = AsyncMock(side_effect=lambda _seconds: calls.append("sleep"))
        component._ctx_reply.side_effect = lambda *_args: calls.append("reply")
        with (
            patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())),
            patch("twitch.components.attendance.asyncio.sleep", sleep_mock),
        ):
            await _checkin(component, ctx)

        sleep_mock.assert_awaited_once_with(5)
        assert calls == ["sleep", "reply"]

    async def test_zero_delay_never_sleeps(self) -> None:
        component = _component()
        ctx = _ctx()
        sleep_mock = AsyncMock()
        with (
            patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())),
            patch("twitch.components.attendance.asyncio.sleep", sleep_mock),
        ):
            await _checkin(component, ctx)

        sleep_mock.assert_not_awaited()


@pytest.mark.asyncio
class TestRankCommand:
    async def test_guard_denial_does_not_touch_attendance(self) -> None:
        component = _component()
        with patch(PATCH_CHECK, AsyncMock(return_value=None)):
            await _rank(component, _ctx())

        component.attendance.get_rank.assert_not_awaited()
        component._ctx_reply.assert_not_awaited()

    async def test_replies_with_checkin_based_rank_and_records_usage(self) -> None:
        component = _component()
        ctx = _ctx()
        with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
            await _rank(component, ctx)

        component.attendance.get_rank.assert_awaited_once_with("ch1", "u1")
        component._ctx_reply.assert_awaited_once_with(
            ctx, "每當點名你都在！能在 132 人中排到【第 8 名】，累積簽到 12 天，絕對是真愛 GivePLZ "
        )
        component._record_command.assert_awaited_once_with(ctx, "rank")

    async def test_broadcaster_gets_a_normal_rank_reply(self) -> None:
        component = _component()
        ctx = _ctx(broadcaster=True)
        with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
            await _rank(component, ctx)

        component.attendance.get_rank.assert_awaited_once_with("ch1", "ch1")
        component._ctx_reply.assert_awaited_once()

    async def test_no_checkin_history_prompts_to_check_in_and_records_usage(self) -> None:
        component = _component()
        component.attendance.get_rank.return_value = None
        ctx = _ctx()
        with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
            await _rank(component, ctx)

        component._ctx_reply.assert_awaited_once_with(ctx, "還沒有簽到紀錄，先去簽到再來看排名吧")
        component._record_command.assert_awaited_once_with(ctx, "rank")

    async def test_lookup_failure_replies_without_recording_usage(self) -> None:
        component = _component()
        component.attendance.get_rank.side_effect = RuntimeError("db unavailable")
        ctx = _ctx()
        with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
            await _rank(component, ctx)

        component._ctx_reply.assert_awaited_once_with(ctx, "排名查詢失敗，請稍後再試")
        component._record_command.assert_not_awaited()


@pytest.mark.asyncio
class TestDevelopmentOverlayCommand:
    async def test_broadcaster_can_publish_preview_in_development(self) -> None:
        component = _component()
        component._is_development = True
        ctx = _ctx(broadcaster=True)

        await _ovltest(component, ctx, count=8)

        component.overlay.publish_checkin_preview.assert_awaited_once_with(
            channel_id="ch1",
            actor_user_id="ch1",
            actor_display_name="Alice",
            total_days=8,
        )
        component.attendance.check_in_with_reply.assert_not_awaited()
        component._ctx_reply.assert_awaited_once_with(ctx, "OVL 測試事件已送出：第 8 天")

    async def test_production_never_publishes_preview(self) -> None:
        component = _component()
        component._is_development = False

        await _ovltest(component, _ctx(broadcaster=True), count=8)

        component.overlay.publish_checkin_preview.assert_not_awaited()

    async def test_non_broadcaster_cannot_publish_preview(self) -> None:
        component = _component()
        component._is_development = True

        await _ovltest(component, _ctx(broadcaster=False), count=8)

        component.overlay.publish_checkin_preview.assert_not_awaited()

    async def test_invalid_count_returns_usage_without_event(self) -> None:
        component = _component()
        component._is_development = True
        ctx = _ctx(broadcaster=True)

        await _ovltest(component, ctx, count=0)

        component.overlay.publish_checkin_preview.assert_not_awaited()
        component._ctx_reply.assert_awaited_once_with(ctx, "用法：!ovltest [1-9999]")

    async def test_publish_failure_returns_dev_error(self) -> None:
        component = _component()
        component._is_development = True
        component.overlay.publish_checkin_preview.side_effect = RuntimeError("db unavailable")
        ctx = _ctx(broadcaster=True)

        await _ovltest(component, ctx, count=7)

        component._ctx_reply.assert_awaited_once_with(ctx, "OVL 測試事件送出失敗")


@pytest.mark.asyncio
async def test_component_refresh_and_live_usage_recording() -> None:
    component = _component()
    new_pool = MagicMock()

    component.refresh_pool(new_pool)

    assert component.cmd_repo.pool is new_pool
    assert component.attendance.repository.pool is new_pool
    assert component.overlay.repository.pool is new_pool

    component.cmd_repo.increment_usage_count = AsyncMock()
    component.bot.analytics.record_command_usage = AsyncMock()
    ctx = _ctx()
    await AttendanceComponent._record_command(component, ctx, "checkin")

    component.cmd_repo.increment_usage_count.assert_awaited_once_with("ch1", "checkin")
    component.bot.analytics.record_command_usage.assert_awaited_once_with(
        session_id=42,
        channel_id="ch1",
        command_name="!checkin",
    )
