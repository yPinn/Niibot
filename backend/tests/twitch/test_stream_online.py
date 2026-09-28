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


def _make_bot(*, needs_reauth: set[str] | None = None, bot_not_mod: set[str] | None = None):
    with (
        patch("twitch.core.bot._MessageRouterMixin.__init__", return_value=None),
        patch("twitch.core.bot._NotifyMixin.__init__", return_value=None),
        patch("twitch.core.bot.commands.AutoBot.__init__", return_value=None),
    ):
        from twitch.core.bot import Bot

        b = Bot.__new__(Bot)
        b._bot_id = "999"
        b._needs_reauth = needs_reauth if needs_reauth is not None else set()
        b._bot_not_mod = bot_not_mod if bot_not_mod is not None else set()
        b.sender_for = MagicMock(return_value="999")
        b.sessions = MagicMock()
        b.sessions.on_stream_online = AsyncMock()
        b.sessions.on_stream_offline = AsyncMock()
        # Default: a no-op recheck that doesn't change mod state — individual
        # tests override with a side_effect to simulate a real check's outcome.
        b._check_bot_mod_status = AsyncMock()
        b._send_mod_request_message = AsyncMock()
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


# ---------------------------------------------------------------------------
# Tests — mod status recheck + once-per-stream reminder
# ---------------------------------------------------------------------------


async def test_mod_status_rechecked_on_every_go_live():
    """Going live is a natural once-per-stream recheck point (catches /mod
    granted with no other trigger due)."""
    bot = _make_bot()
    payload = _make_payload(channel_id="123")

    await bot.event_stream_online(payload)

    bot._check_bot_mod_status.assert_awaited_once_with("123")


async def test_mod_reminder_sent_when_still_not_mod_after_recheck():
    """Was already confirmed not-mod, and stays not-mod after the go-live
    recheck → remind once, since the broadcaster is presumably watching now."""
    bot = _make_bot(bot_not_mod={"123"})
    payload = _make_payload(channel_id="123")

    await bot.event_stream_online(payload)

    bot._send_mod_request_message.assert_awaited_once_with("123")


async def test_no_mod_reminder_when_newly_confirmed_not_mod():
    """A recheck that *newly* confirms not-mod already sent its own prompt
    from inside _check_bot_mod_status — event_stream_online must not double-send."""
    bot = _make_bot(bot_not_mod=set())

    async def _newly_not_mod(channel_id):
        bot._bot_not_mod.add(channel_id)

    bot._check_bot_mod_status = AsyncMock(side_effect=_newly_not_mod)
    payload = _make_payload(channel_id="123")

    await bot.event_stream_online(payload)

    bot._send_mod_request_message.assert_not_awaited()


async def test_no_mod_reminder_when_recheck_confirms_mod():
    """Was confirmed not-mod, but the go-live recheck now confirms mod → no reminder."""
    bot = _make_bot(bot_not_mod={"123"})

    async def _now_mod(channel_id):
        bot._bot_not_mod.discard(channel_id)

    bot._check_bot_mod_status = AsyncMock(side_effect=_now_mod)
    payload = _make_payload(channel_id="123")

    await bot.event_stream_online(payload)

    bot._send_mod_request_message.assert_not_awaited()
