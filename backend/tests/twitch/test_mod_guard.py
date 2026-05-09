"""Tests for twitch.utils.mod_guard — ModGuardNotifier."""

from __future__ import annotations

import os

os.environ.setdefault("TWITCH_CLIENT_ID", "test-client-id")
os.environ.setdefault("TWITCH_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("BOT_ID", "999")
os.environ.setdefault("OWNER_ID", "111")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("ENVIRONMENT", "production")

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from utils.mod_guard import ModGuardNotifier


class TestModGuardNotifier:
    pytestmark = pytest.mark.asyncio

    def _notifier(self) -> ModGuardNotifier:
        return ModGuardNotifier()

    async def test_first_call_sends_message_and_returns_true(self):
        notifier = self._notifier()
        send_fn = AsyncMock()
        result = await notifier.notify("alice", "ch1", "niibot_", send_fn)
        assert result is True
        send_fn.assert_awaited_once()

    async def test_message_mentions_broadcaster_and_bot_login(self):
        notifier = self._notifier()
        captured: list[str] = []

        async def capture(msg: str) -> None:
            captured.append(msg)

        await notifier.notify("alice", "ch1", "niibot_", capture)
        assert captured
        assert "alice" in captured[0]
        assert "niibot_" in captured[0]

    async def test_second_call_within_cooldown_skips_send(self):
        notifier = self._notifier()
        send_fn = AsyncMock()
        await notifier.notify("alice", "ch1", "niibot_", send_fn)
        send_fn.reset_mock()

        result = await notifier.notify("alice", "ch1", "niibot_", send_fn)
        assert result is False
        send_fn.assert_not_awaited()

    async def test_send_allowed_after_cooldown_expires(self):
        notifier = self._notifier()
        send_fn = AsyncMock()
        notifier._last_notified["ch1"] = datetime.now(UTC) - timedelta(hours=2)

        result = await notifier.notify("alice", "ch1", "niibot_", send_fn)
        assert result is True
        send_fn.assert_awaited_once()

    async def test_different_channels_have_independent_cooldowns(self):
        notifier = self._notifier()
        send_fn = AsyncMock()
        await notifier.notify("alice", "ch1", "niibot_", send_fn)

        result = await notifier.notify("bob", "ch2", "niibot_", send_fn)
        assert result is True
        assert send_fn.await_count == 2

    async def test_send_exception_does_not_propagate(self):
        notifier = self._notifier()
        send_fn = AsyncMock(side_effect=Exception("chat unavailable"))
        result = await notifier.notify("alice", "ch1", "niibot_", send_fn)
        assert result is True

    async def test_cooldown_recorded_even_on_failed_send(self):
        """Cooldown is set before the send so a broken chat won't cause notification spam."""
        notifier = self._notifier()
        send_fn = AsyncMock(side_effect=Exception("chat unavailable"))
        await notifier.notify("alice", "ch1", "niibot_", send_fn)
        assert "ch1" in notifier._last_notified

    async def test_notify_skips_in_development(self):
        notifier = self._notifier()
        send_fn = AsyncMock()
        with patch("utils.mod_guard.get_settings") as mock_settings:
            mock_settings.return_value.is_development = True
            result = await notifier.notify("alice", "ch1", "niibot_", send_fn)
        assert result is False
        send_fn.assert_not_awaited()
