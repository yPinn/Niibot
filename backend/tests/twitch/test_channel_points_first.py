"""頭香 (first-of-the-day) redemption: custom announcement template/color."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from twitch.components.channel_points import ChannelPointsComponent

from shared.models.command_config import RedemptionConfig


def _make_component() -> tuple[ChannelPointsComponent, MagicMock]:
    bot = MagicMock()
    bot.token_database = MagicMock()
    bot.bot_id = "bot-1"
    bot.sender_for = MagicMock(return_value="bot-1")
    component = ChannelPointsComponent(bot)
    component.vip_repo.get_reward_rule = AsyncMock(return_value=None)
    component._reply = AsyncMock()  # type: ignore[method-assign]
    return component, bot


def _config(**overrides) -> RedemptionConfig:
    defaults = dict(
        id=1,
        channel_id="channel-1",
        action_type="first",
        reward_name="本日頭香",
        reward_id="reward-first",
        enabled=True,
        first_message="$(@user) 恭喜你搶到沙發！",
        first_announce_color="primary",
    )
    defaults.update(overrides)
    return RedemptionConfig(**defaults)


def _payload() -> MagicMock:
    payload = MagicMock()
    payload.id = "redemption-1"
    payload.broadcaster.id = "channel-1"
    payload.broadcaster.name = "streamer"
    payload.broadcaster.send_announcement = AsyncMock()
    payload.user.id = "viewer-1"
    payload.user.name = "viewer"
    payload.user.display_name = "Viewer"
    payload.reward.id = "reward-first"
    payload.reward.title = "本日頭香"
    payload.reward.cost = 100
    return payload


@pytest.mark.asyncio
async def test_first_redemption_renders_custom_template_and_color():
    component, _ = _make_component()
    component.redemption_repo.find_by_reward = AsyncMock(
        return_value=_config(
            first_message="$(user) 是今天最快的！",
            first_announce_color="green",
        )
    )
    payload = _payload()

    await component._handle_redemption(payload)

    payload.broadcaster.send_announcement.assert_awaited_once_with(
        message="Viewer 是今天最快的！",
        moderator="bot-1",
        color="green",
    )
    component._reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_first_redemption_mention_variable_expands_with_at_sign():
    component, _ = _make_component()
    component.redemption_repo.find_by_reward = AsyncMock(return_value=_config())
    payload = _payload()

    await component._handle_redemption(payload)

    payload.broadcaster.send_announcement.assert_awaited_once_with(
        message="@Viewer 恭喜你搶到沙發！",
        moderator="bot-1",
        color="primary",
    )


@pytest.mark.asyncio
async def test_first_redemption_falls_back_to_same_message_on_announcement_failure():
    component, _ = _make_component()
    component.redemption_repo.find_by_reward = AsyncMock(
        return_value=_config(first_message="$(@user) 恭喜！")
    )
    payload = _payload()
    payload.broadcaster.send_announcement.side_effect = RuntimeError("boom")

    await component._handle_redemption(payload)

    component._reply.assert_awaited_once_with(payload.broadcaster, "@Viewer 恭喜！")
