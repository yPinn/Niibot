"""Tests for _ChannelMixin subscription handling.

Focus areas (master-slave scope migration):
- channel.follow uses moderator_user_id=bot, so a 403 at subscribe time means
  "bot not mod yet" — it must NOT flag the broadcaster for reauth.
- channel.moderator 403 still flags reauth (broadcaster lacks channel:manage:moderators).
- resubscribe_follow (re)creates the follow sub once the bot is granted mod.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio


def _make_bot():
    with (
        patch("twitch.core.bot._MessageRouterMixin.__init__", return_value=None),
        patch("twitch.core.bot._NotifyMixin.__init__", return_value=None),
        patch("twitch.core.bot._SessionMixin.__init__", return_value=None),
        patch("twitch.core.bot.commands.AutoBot.__init__", return_value=None),
    ):
        from twitch.core.bot import Bot

        b = Bot.__new__(Bot)
        b._bot_id = "bot-1"
        b._channel_names = {}
        b._subscribed_channels = set()
        b._subscription_ids = {}
        b._needs_reauth = set()
        b.multi_subscribe = AsyncMock()
        b.delete_eventsub_subscription = AsyncMock()
        return b


def _resp(success=(), errors=()):
    # MultiSubscribeSuccess.response is Twitch's raw payload: id at data[0], not top level.
    return SimpleNamespace(
        success=[SimpleNamespace(response={"data": [{"id": sid}], "total": 1}) for sid in success],
        errors=list(errors),
    )


class TestSubscribeChannelEvents:
    async def test_channel_follow_403_does_not_flag_reauth(self):
        b = _make_bot()
        b.multi_subscribe.return_value = _resp(
            success=["s1"],
            errors=["403 Forbidden ChannelFollowSubscription missing scope"],
        )
        await b.subscribe_channel_events("123")
        assert "123" not in b._needs_reauth
        assert "123" in b._subscribed_channels

    async def test_channel_moderator_403_flags_reauth(self):
        b = _make_bot()
        b.multi_subscribe.return_value = _resp(
            success=["s1"],
            errors=["403 Forbidden ChannelModeratorAddSubscription missing scope"],
        )
        await b.subscribe_channel_events("123")
        assert "123" in b._needs_reauth

    async def test_409_conflicts_are_ignored(self):
        b = _make_bot()
        b.multi_subscribe.return_value = _resp(errors=["409 subscription already exists"])
        await b.subscribe_channel_events("123")
        assert "123" not in b._needs_reauth
        assert "123" in b._subscribed_channels


class TestResubscribeFollow:
    async def test_creates_follow_sub_and_records_id(self):
        b = _make_bot()
        b._subscribed_channels = {"123"}
        b._subscription_ids = {"123": ["existing"]}
        b.multi_subscribe.return_value = _resp(success=["follow-sub-id"])

        await b.resubscribe_follow("123")

        b.multi_subscribe.assert_awaited_once()
        sent = b.multi_subscribe.await_args[0][0]
        assert len(sent) == 1
        assert sent[0].condition["moderator_user_id"] == "bot-1"
        assert b._subscription_ids["123"] == ["existing", "follow-sub-id"]

    async def test_409_is_treated_as_success_noop(self):
        b = _make_bot()
        b._subscribed_channels = {"123"}
        b.multi_subscribe.return_value = _resp(errors=["409 already exists"])

        await b.resubscribe_follow("123")

        assert b._subscription_ids.get("123") is None

    async def test_skips_when_channel_not_subscribed(self):
        b = _make_bot()
        b._subscribed_channels = set()

        await b.resubscribe_follow("123")

        b.multi_subscribe.assert_not_awaited()
