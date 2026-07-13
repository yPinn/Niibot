"""Unit tests for ChannelPointsComponent redemption deduplication.

Twitch EventSub delivers notifications at-least-once, so the same redemption
can be redelivered (observed in production as duplicate log lines around
conduit reconnects). ChannelPointsComponent must process each redemption id
exactly once.

TwitchIO's ``@commands.Component.listener()`` is a thin decorator that just
tags the coroutine function with ``__listener_name__`` and returns it
unchanged (not a descriptor), so the raw method can be invoked directly via
``ChannelPointsComponent.event_custom_redemption_add(component, payload)``.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from twitch.components.channel_points import ChannelPointsComponent


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot.token_database = MagicMock()
    bot._needs_reauth = set()
    bot._bot_is_mod = {"ch_test"}
    bot._mod_check_pending = set()
    return bot


def _make_payload(*, redemption_id: str = "redemption-1") -> MagicMock:
    payload = MagicMock()
    payload.id = redemption_id
    payload.broadcaster.name = "streamer"
    payload.broadcaster.id = "ch_test"
    payload.user.display_name = "Viewer"
    payload.user.name = "viewer"
    payload.user.id = "user123"
    payload.reward.title = "好笑!!!!"
    payload.reward.cost = 5
    payload.user_input = ""
    return payload


@pytest.fixture()
def component() -> ChannelPointsComponent:
    comp = ChannelPointsComponent(_make_bot())
    comp._handle_redemption = AsyncMock()  # type: ignore[method-assign]
    return comp


async def _fire(component: ChannelPointsComponent, payload: MagicMock) -> None:
    await ChannelPointsComponent.event_custom_redemption_add(component, payload)


class TestRedemptionDedup:
    async def test_first_delivery_is_processed(self, component: ChannelPointsComponent) -> None:
        payload = _make_payload()
        await _fire(component, payload)
        component._handle_redemption.assert_awaited_once_with(payload)

    async def test_redelivery_of_same_id_is_ignored(
        self, component: ChannelPointsComponent
    ) -> None:
        payload = _make_payload(redemption_id="redemption-dup")
        await _fire(component, payload)
        await _fire(component, payload)
        await _fire(component, payload)
        component._handle_redemption.assert_awaited_once_with(payload)

    async def test_different_ids_are_each_processed(
        self, component: ChannelPointsComponent
    ) -> None:
        first = _make_payload(redemption_id="redemption-a")
        second = _make_payload(redemption_id="redemption-b")
        await _fire(component, first)
        await _fire(component, second)
        assert component._handle_redemption.await_count == 2
