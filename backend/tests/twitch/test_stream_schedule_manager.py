"""Unit tests for twitch.components.stream_schedule_manager.

Covers: go-live always applies (force=True), the poll skips a channel whose
resolved segment hasn't changed, a changed segment re-applies, and a
scope error marks the channel for reauth instead of raising.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from twitch.components.stream_schedule_manager import StreamScheduleManagerComponent

CHANNEL_ID = "ch_test"


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot.sessions.live_channels = frozenset({CHANNEL_ID})
    bot.channels.get_channel = AsyncMock(return_value=MagicMock(channel_name="streamer"))
    user = MagicMock()
    user.modify_channel = AsyncMock()
    bot.fetch_users = AsyncMock(return_value=[user])
    bot._mark_reauth_required = AsyncMock()
    return bot


def _resolved(segment_id: int = 1, *, title: str = "", game_id: str | None = "123"):
    schedule = MagicMock()
    segment = MagicMock()
    segment.id = segment_id
    segment.title_template = title
    segment.game_id = game_id
    resolved = MagicMock()
    resolved.schedule = schedule
    resolved.segment = segment
    return resolved


@pytest.fixture()
def component() -> StreamScheduleManagerComponent:
    comp = StreamScheduleManagerComponent(_make_bot())
    comp.service = AsyncMock()
    return comp


class TestApplyIfChanged:
    @pytest.mark.asyncio
    async def test_no_resolution_is_a_noop(self, component: StreamScheduleManagerComponent) -> None:
        component.service.resolve_for_channel = AsyncMock(return_value=None)

        await component._apply_if_changed(CHANNEL_ID, force=True)

        component.bot.fetch_users.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_go_live_applies_game_id(self, component: StreamScheduleManagerComponent) -> None:
        component.service.resolve_for_channel = AsyncMock(return_value=_resolved(game_id="123"))

        await component._apply_if_changed(CHANNEL_ID, force=True)

        component.bot.fetch_users.assert_awaited_once()
        user = component.bot.fetch_users.return_value[0]
        user.modify_channel.assert_awaited_once_with(game_id="123")
        assert component._last_applied_segment[CHANNEL_ID] == 1

    @pytest.mark.asyncio
    async def test_poll_skips_when_segment_unchanged(
        self, component: StreamScheduleManagerComponent
    ) -> None:
        component.service.resolve_for_channel = AsyncMock(return_value=_resolved(segment_id=1))
        component._last_applied_segment[CHANNEL_ID] = 1

        await component._apply_if_changed(CHANNEL_ID, force=False)

        component.bot.fetch_users.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_poll_reapplies_when_segment_changed(
        self, component: StreamScheduleManagerComponent
    ) -> None:
        component.service.resolve_for_channel = AsyncMock(return_value=_resolved(segment_id=2))
        component._last_applied_segment[CHANNEL_ID] = 1

        await component._apply_if_changed(CHANNEL_ID, force=False)

        component.bot.fetch_users.assert_awaited_once()
        assert component._last_applied_segment[CHANNEL_ID] == 2

    @pytest.mark.asyncio
    async def test_scope_error_marks_reauth_instead_of_raising(
        self, component: StreamScheduleManagerComponent
    ) -> None:
        component.service.resolve_for_channel = AsyncMock(return_value=_resolved())
        user = component.bot.fetch_users.return_value[0]
        user.modify_channel = AsyncMock(side_effect=RuntimeError("missing scope"))

        import twitch.components.stream_schedule_manager as mod

        real_is_scope_error = mod.is_scope_error
        mod.is_scope_error = lambda e: True
        try:
            await component._apply_if_changed(CHANNEL_ID, force=True)
        finally:
            mod.is_scope_error = real_is_scope_error

        component.bot._mark_reauth_required.assert_awaited_once_with(CHANNEL_ID)
        assert CHANNEL_ID not in component._last_applied_segment

    @pytest.mark.asyncio
    async def test_no_matching_segment_clears_tracking(
        self, component: StreamScheduleManagerComponent
    ) -> None:
        component.service.resolve_for_channel = AsyncMock(return_value=None)
        component._last_applied_segment[CHANNEL_ID] = 1

        await component._apply_if_changed(CHANNEL_ID, force=False)

        assert CHANNEL_ID not in component._last_applied_segment


class TestPollLoop:
    @pytest.mark.asyncio
    async def test_poll_loop_checks_only_live_channels(
        self, component: StreamScheduleManagerComponent
    ) -> None:
        component.service.resolve_for_channel = AsyncMock(return_value=None)

        await component._poll_loop()

        component.service.resolve_for_channel.assert_awaited_once()
        called_channel = component.service.resolve_for_channel.call_args.args[0]
        assert called_channel == CHANNEL_ID
