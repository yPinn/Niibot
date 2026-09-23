"""Tests for Bot.event_stream_online / event_stream_offline.

The session lifecycle itself lives in SessionService (see test_session_service);
here we only check the Bot listener: reauth notification on go-live and
delegation to sessions.on_stream_online / on_stream_offline.
"""

from __future__ import annotations

import os

os.environ.setdefault("TWITCH_CLIENT_ID", "test-client-id")
os.environ.setdefault("TWITCH_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("BOT_ID", "999")
os.environ.setdefault("OWNER_ID", "111")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


def _make_payload(channel_id: str = "123", broadcaster_name: str = "streamer"):
    payload = MagicMock()
    payload.broadcaster = MagicMock()
    payload.broadcaster.id = channel_id
    payload.broadcaster.name = broadcaster_name
    payload.broadcaster.send_message = AsyncMock()
    return payload


def _make_bot(*, needs_reauth: set[str] | None = None):
    with (
        patch("twitch.core.bot._MessageRouterMixin.__init__", return_value=None),
        patch("twitch.core.bot._NotifyMixin.__init__", return_value=None),
        patch("twitch.core.bot.commands.AutoBot.__init__", return_value=None),
    ):
        from twitch.core.bot import Bot

        b = Bot.__new__(Bot)
        b._bot_id = "999"
        b._needs_reauth = needs_reauth if needs_reauth is not None else set()
        b.sender_for = MagicMock(return_value="999")
        b.sessions = MagicMock()
        b.sessions.on_stream_online = AsyncMock()
        b.sessions.on_stream_offline = AsyncMock()
        return b


async def test_reauth_notified_on_go_live_when_needs_reauth():
    """No cooldown gating: this event fires once per real stream, so it
    always announces if the channel is still flagged when it fires."""
    bot = _make_bot(needs_reauth={"123"})
    payload = _make_payload(channel_id="123")

    with patch("core.config.get_settings") as mock_settings:
        mock_settings.return_value.is_production = True
        mock_settings.return_value.frontend_url = "https://niibot.tv"
        await bot.event_stream_online(payload)

    payload.broadcaster.send_message.assert_awaited_once()
    assert "streamer" in payload.broadcaster.send_message.call_args.kwargs["message"]
    bot.sessions.on_stream_online.assert_awaited_once_with("123")


async def test_no_reauth_notification_when_scopes_ok():
    bot = _make_bot(needs_reauth=set())
    payload = _make_payload(channel_id="123")

    await bot.event_stream_online(payload)

    payload.broadcaster.send_message.assert_not_awaited()
    bot.sessions.on_stream_online.assert_awaited_once_with("123")


async def test_stream_offline_delegates_to_service():
    bot = _make_bot()
    payload = _make_payload(channel_id="123")
    await bot.event_stream_offline(payload)
    bot.sessions.on_stream_offline.assert_awaited_once_with("123")
