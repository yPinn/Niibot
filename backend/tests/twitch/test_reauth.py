"""Tests for twitch.utils.reauth — is_scope_error and ReauthNotifier."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from utils.reauth import ReauthNotifier, is_scope_error

# ---------------------------------------------------------------------------
# is_scope_error
# ---------------------------------------------------------------------------


class TestIsScopeError:
    def test_none_returns_false(self):
        assert is_scope_error(None) is False

    def test_non_401_with_scope_message_returns_false(self):
        class Resp:
            status_code = 403
            message = "Missing scope: channel:manage:moderators"

        assert is_scope_error(Resp()) is False

    def test_401_without_scope_message_returns_false(self):
        class Resp:
            status_code = 401
            message = "Invalid token"

        assert is_scope_error(Resp()) is False

    def test_401_with_scope_in_message_attr_returns_true(self):
        class Resp:
            status_code = 401
            message = "Missing scope: channel:manage:moderators"

        assert is_scope_error(Resp()) is True

    def test_twitchio_exception_uses_status_not_status_code(self):
        """TwitchIO HTTPException exposes .status (int), not .status_code."""

        class TwitchError:
            status = 401
            message = "Missing scope: moderator:manage:announcements"

        assert is_scope_error(TwitchError()) is True

    def test_json_body_with_scope_message_returns_true(self):
        """httpx.Response carries the message in its JSON body."""

        class Resp:
            status_code = 401

            def json(self):
                return {"message": "Missing scope: channel:read:subscriptions"}

        assert is_scope_error(Resp()) is True

    def test_json_body_without_scope_message_returns_false(self):
        class Resp:
            status_code = 401

            def json(self):
                return {"message": "Invalid OAuth token"}

        assert is_scope_error(Resp()) is False

    def test_stringified_fallback_returns_true(self):
        class Resp:
            status_code = 401

            def __str__(self):
                return "HTTPStatusError 401 Missing scope: bits:read"

        assert is_scope_error(Resp()) is True

    def test_200_response_returns_false(self):
        class Resp:
            status_code = 200
            message = "OK"

        assert is_scope_error(Resp()) is False

    def test_arbitrary_string_without_status_returns_false(self):
        assert is_scope_error("Missing scope: whatever") is False


# ---------------------------------------------------------------------------
# ReauthNotifier
# ---------------------------------------------------------------------------


class TestReauthNotifier:
    pytestmark = pytest.mark.asyncio

    @pytest.fixture(autouse=True)
    def _production_settings(self):
        with patch("utils.reauth.get_settings") as settings:
            settings.return_value.is_production = True
            settings.return_value.frontend_url = "https://niibot.tv"
            yield

    def _notifier(self) -> ReauthNotifier:
        return ReauthNotifier()

    async def test_first_call_sends_message_and_returns_true(self):
        notifier = self._notifier()
        send_fn = AsyncMock()
        result = await notifier.notify("alice", "ch1", send_fn)
        assert result is True
        send_fn.assert_awaited_once()

    async def test_message_mentions_broadcaster(self):
        notifier = self._notifier()
        captured: list[str] = []

        async def capture(msg: str) -> None:
            captured.append(msg)

        await notifier.notify("alice", "ch1", capture)
        assert captured
        assert "alice" in captured[0]

    async def test_message_contains_frontend_url(self):
        notifier = self._notifier()
        captured: list[str] = []

        async def capture(msg: str) -> None:
            captured.append(msg)

        await notifier.notify("alice", "ch1", capture)
        assert "niibot.tv" in captured[0]
        assert "/docs/get-started" not in captured[0]

    async def test_second_call_within_cooldown_skips_send(self):
        notifier = self._notifier()
        send_fn = AsyncMock()
        await notifier.notify("alice", "ch1", send_fn)
        send_fn.reset_mock()

        result = await notifier.notify("alice", "ch1", send_fn)
        assert result is False
        send_fn.assert_not_awaited()

    async def test_send_allowed_after_cooldown_expires(self):
        notifier = self._notifier()
        send_fn = AsyncMock()
        # Back-date the last notification by more than 1 hour
        notifier._last_notified["ch1"] = datetime.now(UTC) - timedelta(hours=2)

        result = await notifier.notify("alice", "ch1", send_fn)
        assert result is True
        send_fn.assert_awaited_once()

    async def test_different_channels_have_independent_cooldowns(self):
        notifier = self._notifier()
        send_fn = AsyncMock()
        await notifier.notify("alice", "ch1", send_fn)

        result = await notifier.notify("bob", "ch2", send_fn)
        assert result is True
        assert send_fn.await_count == 2

    async def test_send_exception_does_not_propagate(self):
        """A broken send_fn must not crash the caller — notify still returns True."""
        notifier = self._notifier()
        send_fn = AsyncMock(side_effect=Exception("chat unavailable"))
        result = await notifier.notify("alice", "ch1", send_fn)
        assert result is True

    async def test_cooldown_not_recorded_on_failed_send(self):
        """After a failed send, the cooldown timestamp is still set so we don't spam."""
        notifier = self._notifier()
        send_fn = AsyncMock(side_effect=Exception("chat unavailable"))
        await notifier.notify("alice", "ch1", send_fn)
        # The timestamp must have been recorded (cooldown enforced even on failure)
        assert "ch1" in notifier._last_notified

    async def test_notify_skips_in_non_prod(self):
        """No chat message sent outside production — returns False immediately."""
        notifier = self._notifier()
        send_fn = AsyncMock()
        with patch("utils.reauth.get_settings") as mock_settings:
            mock_settings.return_value.is_production = False
            result = await notifier.notify("alice", "ch1", send_fn)
        assert result is False
        send_fn.assert_not_awaited()

    async def test_notify_skips_in_staging(self):
        """Staging environment must not send reauth notifications."""
        notifier = self._notifier()
        send_fn = AsyncMock()
        with patch("utils.reauth.get_settings") as mock_settings:
            mock_settings.return_value.is_production = False  # staging is not production
            result = await notifier.notify("alice", "ch1", send_fn)
        assert result is False
        send_fn.assert_not_awaited()

    async def test_min_interval_allows_send_within_default_cooldown(self):
        """min_interval=5min allows a second send before the 1hr default cooldown."""
        notifier = self._notifier()
        send_fn = AsyncMock()
        # First send (stream-online path, default 1hr cooldown)
        await notifier.notify("alice", "ch1", send_fn)
        send_fn.reset_mock()
        # Back-date by 6 minutes (past 5-min cmd cooldown, still within 1hr)
        notifier._last_notified["ch1"] = datetime.now(UTC) - timedelta(minutes=6)

        result = await notifier.notify("alice", "ch1", send_fn, min_interval=timedelta(minutes=5))
        assert result is True
        send_fn.assert_awaited_once()

    async def test_min_interval_still_gates_within_short_cooldown(self):
        """min_interval=5min blocks a second send within 5 minutes."""
        notifier = self._notifier()
        send_fn = AsyncMock()
        await notifier.notify("alice", "ch1", send_fn, min_interval=timedelta(minutes=5))
        send_fn.reset_mock()

        result = await notifier.notify("alice", "ch1", send_fn, min_interval=timedelta(minutes=5))
        assert result is False
        send_fn.assert_not_awaited()
