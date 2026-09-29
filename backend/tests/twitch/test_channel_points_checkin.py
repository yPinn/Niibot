"""Read-only Channel Points adapter for daily check-in."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from twitch.components.channel_points import ChannelPointsComponent

from shared.models.attendance import (
    CheckinReply,
    CheckinResult,
    CheckinStatus,
    CheckinUnavailable,
)

_REDEEMED_AT = datetime(2026, 9, 29, 15, 55, tzinfo=UTC)


def _make_component() -> tuple[ChannelPointsComponent, MagicMock]:
    bot = MagicMock()
    bot.token_database = MagicMock()
    bot.sessions.session_id.return_value = 42
    component = ChannelPointsComponent(bot)
    component.vip_repo.get_reward_rule = AsyncMock(return_value=None)
    component.redemption_repo.find_by_reward = AsyncMock(
        return_value=MagicMock(action_type="checkin")
    )
    component.attendance.check_in_with_reply = AsyncMock(
        return_value=MagicMock(message="@Viewer 簽到成功，累積 3 天！", delay_seconds=0)
    )
    component._reply = AsyncMock()  # type: ignore[method-assign]
    return component, bot


def _payload() -> MagicMock:
    payload = MagicMock()
    payload.id = "redemption-1"
    payload.broadcaster.id = "channel-1"
    payload.broadcaster.name = "streamer"
    payload.user.id = "viewer-1"
    payload.user.name = "viewer"
    payload.user.display_name = "Viewer"
    payload.reward.id = "reward-checkin"
    payload.reward.title = "每日簽到"
    payload.reward.cost = 10
    payload.redeemed_at = _REDEEMED_AT
    payload.refund = AsyncMock()
    return payload


@pytest.mark.asyncio
async def test_checkin_redemption_uses_reward_id_and_shared_attendance_service():
    component, _ = _make_component()
    payload = _payload()

    await component._handle_redemption(payload)

    component.redemption_repo.find_by_reward.assert_awaited_once_with(
        "channel-1", "reward-checkin", "每日簽到"
    )
    component.attendance.check_in_with_reply.assert_awaited_once_with(
        channel_id="channel-1",
        user_id="viewer-1",
        username="viewer",
        display_name="Viewer",
        occurred_at=_REDEEMED_AT,
    )
    component.bot.sessions.session_id.assert_not_called()
    component._reply.assert_awaited_once_with(payload.broadcaster, "@Viewer 簽到成功，累積 3 天！")


@pytest.mark.asyncio
async def test_delayed_redemption_uses_event_time_instead_of_current_session():
    component, bot = _make_component()
    bot.sessions.session_id.return_value = 999
    payload = _payload()

    await component._handle_redemption(payload)

    component.attendance.check_in_with_reply.assert_awaited_once_with(
        channel_id="channel-1",
        user_id="viewer-1",
        username="viewer",
        display_name="Viewer",
        occurred_at=_REDEEMED_AT,
    )
    bot.sessions.session_id.assert_not_called()


@pytest.mark.asyncio
async def test_offline_redemption_replies_immediately_without_refund():
    component, _ = _make_component()
    payload = _payload()
    component.attendance.check_in_with_reply.return_value = CheckinReply(
        result=CheckinUnavailable(
            channel_id="channel-1",
            user_id="viewer-1",
            username="viewer",
            display_name="Viewer",
            occurred_at=_REDEEMED_AT,
        ),
        message="@Viewer 目前未開台，開台後再簽到吧！",
    )
    sleep_mock = AsyncMock()

    with patch("twitch.components.channel_points.asyncio.sleep", sleep_mock):
        await component._handle_redemption(payload)

    sleep_mock.assert_not_awaited()
    component._reply.assert_awaited_once_with(
        payload.broadcaster, "@Viewer 目前未開台，開台後再簽到吧！"
    )
    payload.refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_redemption_uses_broadcast_day_wording_without_refund():
    component, _ = _make_component()
    payload = _payload()
    component.attendance.check_in_with_reply.return_value = CheckinReply(
        result=CheckinResult(
            status=CheckinStatus.ALREADY_CHECKED_IN,
            channel_id="channel-1",
            user_id="viewer-1",
            username="viewer",
            display_name="Viewer",
            checkin_date=date(2026, 9, 29),
            total_days=3,
            checkin_id=7,
            event_id=None,
            occurred_at=_REDEEMED_AT,
        ),
        message="@Viewer 本直播日已經簽到過了，目前累積 3 天！",
    )

    await component._handle_redemption(payload)

    component._reply.assert_awaited_once_with(
        payload.broadcaster, "@Viewer 本直播日已經簽到過了，目前累積 3 天！"
    )
    payload.refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_unbound_reward_does_not_create_a_checkin():
    component, _ = _make_component()
    component.redemption_repo.find_by_reward.return_value = None

    await component._handle_redemption(_payload())

    component.attendance.check_in_with_reply.assert_not_awaited()
    component._reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_configured_delay_sleeps_before_the_chat_reply():
    component, _ = _make_component()
    component.attendance.check_in_with_reply.return_value = MagicMock(
        message="@Viewer 簽到成功，累積 3 天！", delay_seconds=5
    )
    calls: list[str] = []
    sleep_mock = AsyncMock(side_effect=lambda _seconds: calls.append("sleep"))
    component._reply.side_effect = lambda *_args: calls.append("reply")

    with patch("twitch.components.channel_points.asyncio.sleep", sleep_mock):
        await component._handle_redemption(_payload())

    sleep_mock.assert_awaited_once_with(5)
    assert calls == ["sleep", "reply"]
