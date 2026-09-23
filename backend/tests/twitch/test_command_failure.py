"""Tests for twitch.utils.command_failure — CommandFailureNotifier."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from utils.command_failure import CommandFailureNotifier

pytestmark = pytest.mark.asyncio


class TestCommandFailureNotifier:
    def _notifier(self) -> CommandFailureNotifier:
        return CommandFailureNotifier()

    async def test_first_failure_sends_and_returns_true(self):
        notifier = self._notifier()
        send_fn = AsyncMock()
        result = await notifier.notify("ch1", "title", "查詢失敗，請稍後再試", send_fn)
        assert result is True
        send_fn.assert_awaited_once_with("查詢失敗，請稍後再試")

    async def test_repeated_failure_within_debounce_is_silent(self):
        notifier = self._notifier()
        send_fn = AsyncMock()
        await notifier.notify("ch1", "title", "msg", send_fn)
        send_fn.reset_mock()

        result = await notifier.notify("ch1", "title", "msg", send_fn)
        assert result is False
        send_fn.assert_not_awaited()

    async def test_failure_after_debounce_window_sends_again(self):
        notifier = self._notifier()
        send_fn = AsyncMock()
        notifier._last_notified[("ch1", "title")] = datetime.now(UTC) - timedelta(minutes=11)

        result = await notifier.notify("ch1", "title", "msg", send_fn)
        assert result is True
        send_fn.assert_awaited_once()

    async def test_different_commands_on_same_channel_are_independent(self):
        notifier = self._notifier()
        send_fn = AsyncMock()
        await notifier.notify("ch1", "title", "msg", send_fn)

        result = await notifier.notify("ch1", "game", "msg", send_fn)
        assert result is True
        assert send_fn.await_count == 2

    async def test_different_channels_on_same_command_are_independent(self):
        notifier = self._notifier()
        send_fn = AsyncMock()
        await notifier.notify("ch1", "title", "msg", send_fn)

        result = await notifier.notify("ch2", "title", "msg", send_fn)
        assert result is True
        assert send_fn.await_count == 2

    async def test_send_exception_does_not_propagate(self):
        notifier = self._notifier()
        send_fn = AsyncMock(side_effect=Exception("chat unavailable"))
        result = await notifier.notify("ch1", "title", "msg", send_fn)
        assert result is True
