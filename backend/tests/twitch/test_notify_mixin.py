"""Tests for _NotifyMixin._handle_channel_toggle and Bot._check_bot_mod_status."""

from __future__ import annotations

import json
import os

os.environ.setdefault("TWITCH_CLIENT_ID", "test-client-id")
os.environ.setdefault("TWITCH_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("BOT_ID", "999")
os.environ.setdefault("OWNER_ID", "111")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core._notify_mixin import _NotifyMixin

# ---------------------------------------------------------------------------
# Minimal concrete stub of _NotifyMixin
# ---------------------------------------------------------------------------


class _FakeSubs:
    """Stand-in for Bot.subs (SubscriptionManager) — mutable set + async mocks."""

    def __init__(self) -> None:
        self._subscribed: set[str] = set()
        self._names: set[str] = set()
        self.subscribe = AsyncMock()
        self.unsubscribe = AsyncMock()

    def is_subscribed(self, cid: str) -> bool:
        return cid in self._subscribed

    @property
    def subscribed(self) -> frozenset[str]:
        return frozenset(self._subscribed)

    def ch(self, cid: str) -> str:
        return cid

    def forget(self, cid: str) -> None:
        self._names.discard(cid)


class _StubMixin(_NotifyMixin):
    """Provides the attributes that _NotifyMixin references via self.*."""

    def __init__(self) -> None:
        self._bot_id = "bot-001"
        self.subs = _FakeSubs()
        self.sessions = MagicMock()
        self.sessions.ensure_session = AsyncMock(return_value=None)
        self._bot_is_mod: set[str] = set()
        self._needs_reauth: set[str] = set()
        self._mod_check_pending: set[str] = set()
        self._check_bot_mod_status = AsyncMock()
        self._send_welcome_message = AsyncMock()
        self.redemption_configs = MagicMock()
        self.redemption_configs.ensure_defaults = AsyncMock()
        self.event_configs = MagicMock()
        self.event_configs.ensure_defaults = AsyncMock()
        self.command_configs = MagicMock()
        self.command_configs.warm_cache = AsyncMock(return_value=0)
        self.owner_id = "owner-001"
        token = MagicMock()
        token.scopes = None  # no missing scopes by default
        self.channels = MagicMock()
        self.channels.get_token = AsyncMock(return_value=token)
        # Default: an admitted (enabled) channel so the admission gate in
        # _handle_new_token passes through. Tests that exercise the gate
        # override get_channel with a disabled channel.
        enabled_channel = MagicMock()
        enabled_channel.enabled = True
        self.channels.get_channel = AsyncMock(return_value=enabled_channel)
        self._components: dict[str, object] = {}

    def _ch(self, cid: str) -> str:
        return self.subs.ch(cid)


def _payload(channel_id: str, *, enabled: bool) -> str:
    return json.dumps({"channel_id": channel_id, "enabled": enabled})


class TestConfigChangeMemoryInvalidation:
    pytestmark = pytest.mark.asyncio

    async def test_refresh_clears_component_channel_memory(self) -> None:
        mixin = _StubMixin()
        component = MagicMock()
        mixin._components["components.ai"] = component

        await mixin._refresh_channel_cache("ch1")

        component.clear_channel_memory.assert_called_once_with("ch1")

    async def test_refresh_tolerates_components_without_memory_hook(self) -> None:
        mixin = _StubMixin()
        mixin._components["components.other"] = object()

        await mixin._refresh_channel_cache("ch1")

        mixin.command_configs.warm_cache.assert_awaited_once_with("ch1")


# ---------------------------------------------------------------------------
# _handle_channel_toggle — DISABLE
# ---------------------------------------------------------------------------


class TestHandleChannelToggleDisable:
    pytestmark = pytest.mark.asyncio

    async def test_disable_discards_bot_is_mod(self):
        mixin = _StubMixin()
        component = MagicMock()
        mixin._components["components.ai"] = component
        mixin.subs._subscribed = {"ch1"}
        mixin._bot_is_mod = {"ch1"}
        mixin._needs_reauth = {"ch1"}
        mixin._mod_check_pending = {"ch1"}
        mixin.subs._names = {"ch1"}

        await mixin._handle_channel_toggle(
            None, None, "channel_toggle", _payload("ch1", enabled=False)
        )

        assert "ch1" not in mixin._bot_is_mod
        assert "ch1" not in mixin._needs_reauth
        assert "ch1" not in mixin._mod_check_pending
        assert "ch1" not in mixin.subs._names
        mixin.subs.unsubscribe.assert_awaited_once_with("ch1")
        component.clear_channel_memory.assert_called_once_with("ch1")

    async def test_disable_not_subscribed_still_cleans_up_state(self):
        """DISABLE for a channel already unsubscribed skips the unsubscribe
        call, but per-channel in-memory state must still be dropped — it can
        be set (e.g. _needs_reauth from a scope check) independently of
        EventSub subscription status, and leaving it would leak across
        disable/re-enable churn for the life of the process."""
        mixin = _StubMixin()
        mixin.subs._subscribed = set()
        mixin._bot_is_mod = {"ch1"}
        mixin._needs_reauth = {"ch1"}
        mixin._mod_check_pending = {"ch1"}
        mixin.subs._names = {"ch1"}

        await mixin._handle_channel_toggle(
            None, None, "channel_toggle", _payload("ch1", enabled=False)
        )

        mixin.subs.unsubscribe.assert_not_awaited()
        assert "ch1" not in mixin._bot_is_mod
        assert "ch1" not in mixin._needs_reauth
        assert "ch1" not in mixin._mod_check_pending
        assert "ch1" not in mixin.subs._names

    async def test_disable_ignores_bot_own_channel(self):
        mixin = _StubMixin()
        mixin.subs._subscribed = {"bot-001"}
        mixin._bot_is_mod = {"bot-001"}

        await mixin._handle_channel_toggle(
            None, None, "channel_toggle", _payload("bot-001", enabled=False)
        )

        mixin.subs.unsubscribe.assert_not_awaited()
        assert "bot-001" in mixin._bot_is_mod  # early-return, unchanged


# ---------------------------------------------------------------------------
# _handle_channel_toggle — ENABLE
# ---------------------------------------------------------------------------


class TestHandleChannelToggleEnable:
    pytestmark = pytest.mark.asyncio

    async def test_enable_calls_check_mod_status_after_subscribe(self):
        mixin = _StubMixin()

        await mixin._handle_channel_toggle(
            None, None, "channel_toggle", _payload("ch2", enabled=True)
        )

        mixin.subs.subscribe.assert_awaited_once_with("ch2")
        mixin._check_bot_mod_status.assert_awaited_once_with("ch2")
        mixin.event_configs.ensure_defaults.assert_awaited_once_with("ch2")

    async def test_enable_already_subscribed_skips_subscribe_and_mod_check(self):
        mixin = _StubMixin()
        mixin.subs._subscribed = {"ch2"}

        await mixin._handle_channel_toggle(
            None, None, "channel_toggle", _payload("ch2", enabled=True)
        )

        mixin.subs.subscribe.assert_not_awaited()
        mixin._check_bot_mod_status.assert_not_awaited()

    async def test_enable_ignores_bot_own_channel(self):
        mixin = _StubMixin()

        await mixin._handle_channel_toggle(
            None, None, "channel_toggle", _payload("bot-001", enabled=True)
        )

        mixin.subs.subscribe.assert_not_awaited()
        mixin._check_bot_mod_status.assert_not_awaited()

    async def test_enable_sets_needs_reauth_when_scopes_missing(self):
        """Valid token with missing scopes → _needs_reauth set after toggle enable."""
        mixin = _StubMixin()
        token = MagicMock()
        # Provide a minimal scope string that is missing required broadcaster scopes
        token.scopes = "user:read:email"
        mixin.channels.get_token = AsyncMock(return_value=token)

        await mixin._handle_channel_toggle(
            None, None, "channel_toggle", _payload("ch3", enabled=True)
        )

        assert "ch3" in mixin._needs_reauth

    async def test_enable_skips_scope_check_when_already_needs_reauth(self):
        """If _check_bot_mod_status already set _needs_reauth (401/403), skip DB scope check."""
        mixin = _StubMixin()

        # Simulate mod check setting _needs_reauth (as it now does for 401/403)
        async def _mod_check_sets_reauth(channel_id):
            mixin._needs_reauth.add(channel_id)

        mixin._check_bot_mod_status = AsyncMock(side_effect=_mod_check_sets_reauth)

        await mixin._handle_channel_toggle(
            None, None, "channel_toggle", _payload("ch3", enabled=True)
        )

        assert "ch3" in mixin._needs_reauth
        # get_token not called for the scope check path
        mixin.channels.get_token.assert_not_awaited()

    async def test_enable_no_reauth_when_all_scopes_present(self):
        """Token with all required broadcaster scopes → _needs_reauth stays empty."""
        from shared.twitch_scopes import BROADCASTER_SCOPES

        mixin = _StubMixin()
        token = MagicMock()
        token.scopes = " ".join(BROADCASTER_SCOPES)
        mixin.channels.get_token = AsyncMock(return_value=token)

        await mixin._handle_channel_toggle(
            None, None, "channel_toggle", _payload("ch3", enabled=True)
        )

        assert "ch3" not in mixin._needs_reauth


# ---------------------------------------------------------------------------
# _handle_new_token — reauth-restored message
# ---------------------------------------------------------------------------


def _new_token_payload(user_id: str) -> str:
    return json.dumps({"user_id": user_id})


def _make_user_info(login: str, scopes: list[str]):

    info = MagicMock()
    info.login = login
    info.scopes = scopes
    return info


class TestHandleNewTokenReauthRestored:
    pytestmark = pytest.mark.asyncio

    async def test_sends_restored_message_when_reauth_cleared(self):
        """When scopes are complete and channel was in _needs_reauth, restored msg is sent."""
        from shared.twitch_scopes import BROADCASTER_SCOPES

        mixin = _StubMixin()
        mixin._needs_reauth = {"u1"}
        mixin._send_reauth_restored_message = AsyncMock()
        mixin.add_token = AsyncMock(return_value=_make_user_info("alice", BROADCASTER_SCOPES))
        mixin.add_channel_to_db = AsyncMock()
        mixin.subs._subscribed = {"u1"}  # already subscribed, skip subscribe branch

        await mixin._handle_new_token(None, None, "new_token", _new_token_payload("u1"))

        mixin._send_reauth_restored_message.assert_awaited_once_with("u1", "alice")
        assert "u1" not in mixin._needs_reauth

    async def test_no_restored_message_when_not_previously_in_reauth(self):
        """No restored message when channel was never in _needs_reauth."""
        from shared.twitch_scopes import BROADCASTER_SCOPES

        mixin = _StubMixin()
        mixin._needs_reauth = set()  # was NOT in reauth
        mixin._send_reauth_restored_message = AsyncMock()
        mixin.add_token = AsyncMock(return_value=_make_user_info("alice", BROADCASTER_SCOPES))
        mixin.add_channel_to_db = AsyncMock()
        mixin.subs._subscribed = {"u1"}

        await mixin._handle_new_token(None, None, "new_token", _new_token_payload("u1"))

        mixin._send_reauth_restored_message.assert_not_awaited()

    async def test_no_restored_message_when_scopes_still_missing(self):
        """No restored message when new token still has missing scopes."""
        mixin = _StubMixin()
        mixin._needs_reauth = {"u1"}
        mixin._send_reauth_restored_message = AsyncMock()
        mixin.add_token = AsyncMock(return_value=_make_user_info("alice", ["user:read:email"]))
        mixin.add_channel_to_db = AsyncMock()
        mixin.subs._subscribed = {"u1"}

        await mixin._handle_new_token(None, None, "new_token", _new_token_payload("u1"))

        mixin._send_reauth_restored_message.assert_not_awaited()
        assert "u1" in mixin._needs_reauth

    async def test_mod_status_rechecked_after_reauth_even_when_already_subscribed(self):
        """After clearing _needs_reauth, _check_bot_mod_status is called for already-subscribed
        channels so _bot_is_mod is populated (was empty if token expired at startup)."""
        from shared.twitch_scopes import BROADCASTER_SCOPES

        mixin = _StubMixin()
        mixin._needs_reauth = {"u1"}
        mixin.subs._subscribed = {"u1"}  # already subscribed — would normally skip mod check
        mixin._send_reauth_restored_message = AsyncMock()
        mixin._check_bot_mod_status = AsyncMock()
        mixin.add_token = AsyncMock(return_value=_make_user_info("alice", BROADCASTER_SCOPES))
        mixin.add_channel_to_db = AsyncMock()

        await mixin._handle_new_token(None, None, "new_token", _new_token_payload("u1"))

        mixin._check_bot_mod_status.assert_awaited_once_with("u1")


# ---------------------------------------------------------------------------
# _handle_new_token — admission gate (don't join unapproved channels)
# ---------------------------------------------------------------------------


class TestHandleNewTokenAdmissionGate:
    pytestmark = pytest.mark.asyncio

    async def test_does_not_subscribe_when_channel_disabled(self):
        """A pending/suspended owner's channel has enabled=FALSE: load the token
        but never subscribe (joining is reserved for admitted channels)."""
        from shared.twitch_scopes import BROADCASTER_SCOPES

        mixin = _StubMixin()
        mixin.subs._subscribed = set()  # not yet subscribed
        mixin.add_token = AsyncMock(return_value=_make_user_info("alice", BROADCASTER_SCOPES))
        mixin.add_channel_to_db = AsyncMock()
        disabled_channel = MagicMock()
        disabled_channel.enabled = False
        mixin.channels.get_channel = AsyncMock(return_value=disabled_channel)

        await mixin._handle_new_token(None, None, "new_token", _new_token_payload("u1"))

        mixin.subs.subscribe.assert_not_awaited()
        assert "u1" not in mixin.subs.subscribed

    async def test_does_not_subscribe_when_channel_missing(self):
        """No channels row yet (race during signup) → fail closed, don't join."""
        from shared.twitch_scopes import BROADCASTER_SCOPES

        mixin = _StubMixin()
        mixin.subs._subscribed = set()
        mixin.add_token = AsyncMock(return_value=_make_user_info("alice", BROADCASTER_SCOPES))
        mixin.add_channel_to_db = AsyncMock()
        mixin.channels.get_channel = AsyncMock(return_value=None)

        await mixin._handle_new_token(None, None, "new_token", _new_token_payload("u1"))

        mixin.subs.subscribe.assert_not_awaited()

    async def test_subscribes_when_channel_enabled(self):
        """An admitted (enabled) channel that is not yet subscribed gets joined."""
        from shared.twitch_scopes import BROADCASTER_SCOPES

        mixin = _StubMixin()
        mixin.subs._subscribed = set()
        mixin.add_token = AsyncMock(return_value=_make_user_info("alice", BROADCASTER_SCOPES))
        mixin.add_channel_to_db = AsyncMock()
        # get_channel defaults to an enabled channel via _StubMixin.

        await mixin._handle_new_token(None, None, "new_token", _new_token_payload("u1"))

        mixin.subs.subscribe.assert_awaited_once_with("u1")


# ---------------------------------------------------------------------------
# _handle_token_reauth — cache invalidation + delegation
# ---------------------------------------------------------------------------


class TestHandleTokenReauth:
    pytestmark = pytest.mark.asyncio

    async def test_invalidates_broadcaster_token_cache(self):
        """Re-auth notification must bust the in-process token cache."""
        mixin = _StubMixin()
        mixin.add_token = AsyncMock(return_value=_make_user_info("alice", []))
        mixin.add_channel_to_db = AsyncMock()
        mixin.subs._subscribed = {"u1"}

        with patch("shared.repositories.channel._token_cache") as mock_cache:
            await mixin._handle_token_reauth(None, None, "token_reauth", _new_token_payload("u1"))
            mock_cache.invalidate.assert_called_once_with("token:u1:broadcaster")

    async def test_ignores_bot_own_id(self):
        mixin = _StubMixin()
        mixin.add_token = AsyncMock()

        with patch("shared.repositories.channel._token_cache"):
            await mixin._handle_token_reauth(
                None, None, "token_reauth", _new_token_payload("bot-001")
            )

        mixin.add_token.assert_not_awaited()

    async def test_delegates_to_handle_new_token(self):
        """After cache bust, full _handle_new_token logic runs."""
        from shared.twitch_scopes import BROADCASTER_SCOPES

        mixin = _StubMixin()
        mixin._needs_reauth = {"u1"}
        mixin._send_reauth_restored_message = AsyncMock()
        mixin.add_token = AsyncMock(return_value=_make_user_info("alice", BROADCASTER_SCOPES))
        mixin.add_channel_to_db = AsyncMock()
        mixin.subs._subscribed = {"u1"}

        with patch("shared.repositories.channel._token_cache"):
            await mixin._handle_token_reauth(None, None, "token_reauth", _new_token_payload("u1"))

        # _handle_new_token cleared _needs_reauth and sent restored message
        assert "u1" not in mixin._needs_reauth
        mixin._send_reauth_restored_message.assert_awaited_once_with("u1", "alice")


class TestHandleBotTokenUpdated:
    pytestmark = pytest.mark.asyncio

    async def test_invalidates_bot_cache_and_hot_reloads_credential(self):
        mixin = _StubMixin()
        token = MagicMock(token="encrypted-access", refresh="encrypted-refresh")
        mixin.channels.get_token = AsyncMock(return_value=token)
        mixin.add_token = AsyncMock(return_value=_make_user_info("niibot", []))

        with patch("shared.repositories.channel._token_cache") as mock_cache:
            await mixin._handle_bot_token_updated(
                None,
                None,
                "bot_token_updated",
                _new_token_payload("bot-001"),
            )

        mock_cache.invalidate.assert_called_once_with("token:bot-001:bot")
        mixin.channels.get_token.assert_awaited_once_with("bot-001", "bot")
        mixin.add_token.assert_awaited_once_with("encrypted-access", "encrypted-refresh")

    async def test_missing_updated_credential_fails_closed(self):
        mixin = _StubMixin()
        mixin.channels.get_token = AsyncMock(return_value=None)
        mixin.add_token = AsyncMock()

        await mixin._handle_bot_token_updated(
            None,
            None,
            "bot_token_updated",
            _new_token_payload("bot-001"),
        )

        mixin.add_token.assert_not_awaited()


# ---------------------------------------------------------------------------
# Bot._check_bot_mod_status
# ---------------------------------------------------------------------------


def _make_httpx_ctx(status_code: int, json_data: dict | None = None, text: str = "") -> MagicMock:
    """Build a mock for `async with httpx.AsyncClient(...) as client`."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = text
    if json_data is not None:
        mock_resp.json.return_value = json_data

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.fixture()
def mod_bot():
    """Minimal Bot instance wired only for _check_bot_mod_status."""
    with (
        patch("twitch.core.bot._MessageRouterMixin.__init__", return_value=None),
        patch("twitch.core.bot._NotifyMixin.__init__", return_value=None),
        patch("twitch.core.bot.commands.AutoBot.__init__", return_value=None),
    ):
        from twitch.core.bot import Bot
        from twitch.core.subscription_manager import SubscriptionManager

        b = Bot.__new__(Bot)
        b._bot_id = "bot-001"
        b._client_id = "test-client-id"
        b._bot_is_mod = set()
        b._needs_reauth = set()
        b._mod_check_pending = set()
        b.subs = SubscriptionManager(
            bot_id="bot-001",
            multi_subscribe=AsyncMock(),
            delete_subscription=AsyncMock(),
            needs_reauth=b._needs_reauth,
        )
        b.channels = MagicMock()
        return b


class TestCheckBotModStatus:
    pytestmark = pytest.mark.asyncio

    async def test_adds_to_bot_is_mod_when_api_confirms_mod(self, mod_bot):
        token_obj = MagicMock(token="tok")
        mod_bot.channels.get_token = AsyncMock(return_value=token_obj)
        ctx = _make_httpx_ctx(200, {"data": [{"user_id": "bot-001"}]})

        with patch("twitch.core.bot.httpx.AsyncClient", return_value=ctx):
            await mod_bot._check_bot_mod_status("ch1")

        assert "ch1" in mod_bot._bot_is_mod

    async def test_does_not_add_when_api_returns_empty_data(self, mod_bot):
        token_obj = MagicMock(token="tok")
        mod_bot.channels.get_token = AsyncMock(return_value=token_obj)
        ctx = _make_httpx_ctx(200, {"data": []})

        with patch("twitch.core.bot.httpx.AsyncClient", return_value=ctx):
            await mod_bot._check_bot_mod_status("ch1")

        assert "ch1" not in mod_bot._bot_is_mod

    @pytest.mark.parametrize("status_code", [401, 403])
    async def test_auth_failure_sets_needs_reauth(self, mod_bot, status_code):
        """401 or 403 from Helix → _needs_reauth set, _bot_is_mod not set."""
        token_obj = MagicMock(token="tok")
        mod_bot.channels.get_token = AsyncMock(return_value=token_obj)
        ctx = _make_httpx_ctx(status_code, text="Unauthorized")

        with patch("twitch.core.bot.httpx.AsyncClient", return_value=ctx):
            await mod_bot._check_bot_mod_status("ch1")

        assert "ch1" not in mod_bot._bot_is_mod
        assert "ch1" in mod_bot._needs_reauth

    async def test_no_token_returns_early_without_error(self, mod_bot):
        mod_bot.channels.get_token = AsyncMock(return_value=None)

        await mod_bot._check_bot_mod_status("ch1")  # must not raise

        assert "ch1" not in mod_bot._bot_is_mod

    async def test_network_error_does_not_propagate(self, mod_bot):
        token_obj = MagicMock(token="tok")
        mod_bot.channels.get_token = AsyncMock(return_value=token_obj)

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("network error"))
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("twitch.core.bot.httpx.AsyncClient", return_value=ctx):
            await mod_bot._check_bot_mod_status("ch1")  # must not raise

        assert "ch1" not in mod_bot._bot_is_mod
