"""Tests for event_stream_online — reauth notification on go-live."""

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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_payload(channel_id: str = "123", broadcaster_name: str = "streamer"):
    payload = MagicMock()
    payload.broadcaster = MagicMock()
    payload.broadcaster.id = channel_id
    payload.broadcaster.name = broadcaster_name
    payload.broadcaster.send_message = AsyncMock()
    return payload


def _make_component(*, needs_reauth: set[str] | None = None, has_analytics: bool = False):
    """Build a GeneralCommandsComponent with heavy deps mocked out.

    _has_analytics is a property checking hasattr(bot, "_active_sessions") and
    hasattr(bot, "analytics"). To disable it, omit those attrs from bot.
    """
    with patch("twitch.components.general_commands.get_settings"):
        from twitch.components.general_commands import GeneralCommandsComponent

        comp = GeneralCommandsComponent.__new__(GeneralCommandsComponent)
        bot = MagicMock(spec=[])  # spec=[] → no attrs unless explicitly set
        bot.bot_id = "bot-001"
        bot._needs_reauth = needs_reauth if needs_reauth is not None else set()
        if has_analytics:
            bot._active_sessions = {}
            bot._session_creating = set()
            analytics = MagicMock()
            analytics.create_session = AsyncMock(return_value=42)
            bot.analytics = analytics
            bot.fetch_streams = MagicMock(return_value=_aiter([]))
        comp.bot = bot
        return comp


def _aiter(items):
    """Return an async iterator over items."""

    async def _gen():
        for item in items:
            yield item

    return _gen()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reauth_notified_on_stream_online_when_needs_reauth():
    """When channel is in _needs_reauth, reauth_notifier fires on go-live."""
    comp = _make_component(needs_reauth={"123"})
    payload = _make_payload(channel_id="123")

    with patch("utils.reauth.reauth_notifier") as mock_notifier:
        mock_notifier.notify = AsyncMock(return_value=True)
        await comp.event_stream_online(payload)

    mock_notifier.notify.assert_awaited_once()
    call_kwargs = mock_notifier.notify.call_args.kwargs
    assert call_kwargs["broadcaster_login"] == "streamer"
    assert call_kwargs["channel_id"] == "123"


@pytest.mark.asyncio
async def test_no_reauth_notification_when_scopes_ok():
    """When channel is NOT in _needs_reauth, reauth_notifier is not called."""
    comp = _make_component(needs_reauth=set())
    payload = _make_payload(channel_id="123")

    with patch("utils.reauth.reauth_notifier") as mock_notifier:
        mock_notifier.notify = AsyncMock(return_value=True)
        await comp.event_stream_online(payload)

    mock_notifier.notify.assert_not_called()


@pytest.mark.asyncio
async def test_reauth_fires_even_when_analytics_disabled():
    """Reauth notification must not be blocked by _has_analytics=False early return."""
    comp = _make_component(needs_reauth={"123"}, has_analytics=False)
    payload = _make_payload(channel_id="123")

    with patch("utils.reauth.reauth_notifier") as mock_notifier:
        mock_notifier.notify = AsyncMock(return_value=True)
        await comp.event_stream_online(payload)

    mock_notifier.notify.assert_awaited_once()
