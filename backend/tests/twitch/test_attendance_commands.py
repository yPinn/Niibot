"""Command-level tests for daily check-in and the development OVL trigger."""

from __future__ import annotations

import os

os.environ.setdefault("TWITCH_CLIENT_ID", "test-client-id")
os.environ.setdefault("TWITCH_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("BOT_ID", "999")
os.environ.setdefault("OWNER_ID", "111")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("ENVIRONMENT", "production")

from datetime import UTC, date, datetime  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from twitch.components.attendance import AttendanceComponent  # noqa: E402

from shared.models.attendance import (  # noqa: E402
    CheckinReply,
    CheckinResult,
    CheckinStatus,
)

PATCH_CHECK = "twitch.components.attendance.check_command"
_NOW = datetime(2026, 8, 31, 10, 0, tzinfo=UTC)


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
