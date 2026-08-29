"""Unit tests for twitch.components.timer_manager — TimerManagerComponent.

Covers the manual alias-trigger path (event_message -> _fire_timer), in
particular that it respects the timer's own interval_seconds instead of
firing unconditionally on every matching chat message.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from twitch.components.timer_manager import TimerManagerComponent

CHANNEL_ID = "ch_test"


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot._bot_is_mod = {CHANNEL_ID}
    bot.sessions.line_count = MagicMock(return_value=0)
    bot.sessions.live_channels = frozenset({CHANNEL_ID})
    bot.bot_id = "bot123"
    bot.timer_configs = MagicMock()
    bot.channels = MagicMock()
    bot.channels.get_channel = AsyncMock(return_value=MagicMock(channel_name="streamer"))
    user = MagicMock()
    user.send_announcement = AsyncMock()
    user.send_message = AsyncMock()
    bot.fetch_users = AsyncMock(return_value=[user])
    return bot


def _make_timer(
    *,
    timer_id: int = 1,
    command_alias: str = "socials",
    interval_seconds: int = 300,
) -> MagicMock:
    timer = MagicMock()
    timer.id = timer_id
    timer.command_alias = command_alias
    timer.interval_seconds = interval_seconds
    timer.min_lines = 0
    timer.timer_name = "social"
    timer.message_template = "Follow!"
    timer.announce = False
    return timer


def _make_message(text: str, channel_id: str = CHANNEL_ID) -> MagicMock:
    message = MagicMock()
    message.text = text
    message.broadcaster.id = channel_id
    return message


@pytest.fixture()
def component() -> TimerManagerComponent:
    return TimerManagerComponent(_make_bot())


class TestAliasTrigger:
    @pytest.mark.asyncio
    async def test_first_trigger_fires(self, component: TimerManagerComponent) -> None:
        timer = _make_timer()
        component.bot.timer_configs.list_enabled = AsyncMock(return_value=[timer])

        await component.event_message(_make_message("!socials"))

        component.bot.fetch_users.assert_awaited_once()
        assert component._timer_last_fire[timer.id] is not None

    @pytest.mark.asyncio
    async def test_immediate_repeat_is_suppressed(self, component: TimerManagerComponent) -> None:
        """A viewer spamming the alias must not re-trigger within interval_seconds."""
        timer = _make_timer(interval_seconds=300)
        component.bot.timer_configs.list_enabled = AsyncMock(return_value=[timer])

        await component.event_message(_make_message("!socials"))
        component.bot.fetch_users.reset_mock()

        await component.event_message(_make_message("!socials"))
        await component.event_message(_make_message("!socials"))
        await component.event_message(_make_message("!socials"))

        component.bot.fetch_users.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fires_again_after_interval_elapses(
        self, component: TimerManagerComponent
    ) -> None:
        timer = _make_timer(interval_seconds=300)
        component.bot.timer_configs.list_enabled = AsyncMock(return_value=[timer])
        component._timer_last_fire[timer.id] = datetime.now(UTC) - timedelta(seconds=301)

        await component.event_message(_make_message("!socials"))

        component.bot.fetch_users.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_matching_alias_does_not_fire(self, component: TimerManagerComponent) -> None:
        timer = _make_timer(command_alias="socials")
        component.bot.timer_configs.list_enabled = AsyncMock(return_value=[timer])

        await component.event_message(_make_message("!unrelated"))

        component.bot.fetch_users.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_mod_channel_ignored(self, component: TimerManagerComponent) -> None:
        component.bot._bot_is_mod = set()
        timer = _make_timer()
        component.bot.timer_configs.list_enabled = AsyncMock(return_value=[timer])

        await component.event_message(_make_message("!socials"))

        component.bot.timer_configs.list_enabled.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_command_message_ignored(self, component: TimerManagerComponent) -> None:
        await component.event_message(_make_message("just chatting"))

        component.bot.timer_configs.list_enabled.assert_not_called()
