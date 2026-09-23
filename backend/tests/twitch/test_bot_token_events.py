"""Unit tests for Bot token-event handlers.

Covers:
- event_token_refreshed: persists refreshed tokens + scopes to DB
- event_subscription_revoked: flags reauth on authorization_revoked
- add_token: persists twitchio's current token, not stale call args
- load_tokens: reauth-notification cooldown
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_token_refreshed_payload(
    user_id: str,
    token: str,
    refresh_token: str,
    scopes: list[str] | None = None,
) -> MagicMock:
    payload = MagicMock()
    payload.user_id = user_id
    payload.token = token
    payload.refresh_token = refresh_token
    payload.scopes = scopes if scopes is not None else []
    return payload


def _make_revoked_payload(
    reason: str, *, condition: dict | None = None, sub_type: str = "channel.follow"
) -> MagicMock:
    payload = MagicMock()
    payload.raw = {
        "condition": condition if condition is not None else {"broadcaster_user_id": "ch1"}
    }
    payload.status = MagicMock(value=reason)
    payload.type = sub_type
    return payload


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def bot():
    """Bot instance with heavy deps mocked — minimal surface for token tests."""
    with (
        patch("twitch.core.bot._MessageRouterMixin.__init__", return_value=None),
        patch("twitch.core.bot._NotifyMixin.__init__", return_value=None),
        patch("twitch.core.bot.commands.AutoBot.__init__", return_value=None),
    ):
        from twitch.core.bot import Bot
        from twitch.core.subscription_manager import SubscriptionManager

        from core.bot_resolver import BotAccountResolver

        b = Bot.__new__(Bot)
        b.channels = MagicMock()
        b.channels.upsert_token_only = AsyncMock()
        b.channels.rotate_token_if_revision = AsyncMock(return_value=True)
        b.channels.get_token = AsyncMock()
        b._background_tasks = set()
        b._bot_id = "bot-001"
        b.bots = BotAccountResolver(MagicMock(), system_bot_id="bot-001")
        b._client_id = "test-client-id"
        b._needs_reauth = set()
        b.subs = SubscriptionManager(
            bot_id="bot-001",
            multi_subscribe=AsyncMock(),
            delete_subscription=AsyncMock(),
            needs_reauth=b._needs_reauth,
        )
        b._bot_is_mod = set()
        b._mod_check_pending = set()
        b._token_refresh_buffer = []
        b._token_refresh_flush_task = None
        b._runtime_credential_revisions = {}
        b._pending_refresh_revisions = {}
        b.egress = MagicMock()
        b.egress.acquire_helix = AsyncMock()
        b.egress.acquire_chat = AsyncMock()
        b.egress.observe_helix = MagicMock()
        b.egress.defer_chat = MagicMock()
        return b


class TestBotInit:
    def test_initial_catalog_is_deferred_to_rate_limited_subscription_manager(self):
        captured: dict = {}

        def fake_autobot_init(instance, **kwargs):
            captured.update(kwargs)
            instance.multi_subscribe = AsyncMock()
            instance.delete_eventsub_subscription = AsyncMock()

        with patch("twitch.core.bot.commands.AutoBot.__init__", new=fake_autobot_init):
            from twitch.core.bot import Bot

            Bot(
                client_id="client",
                client_secret="secret",
                bot_id="bot-001",
                owner_id="owner-001",
                conduit_id="conduit-1",
                token_database=MagicMock(),
                db_manager=MagicMock(),
                database_url="postgresql://test",
            )

        assert captured["subscriptions"] == []
        assert captured.get("force_subscribe") is not True


@pytest.mark.asyncio
class TestSubscriptionBootstrap:
    async def test_reconcile_enabled_subscriptions_uses_one_global_diff(self, bot):
        from twitch.core.bot import Bot

        channels = [
            SimpleNamespace(channel_id="ch1", channel_name="One"),
            SimpleNamespace(channel_id="ch2", channel_name="Two"),
            SimpleNamespace(channel_id=bot._bot_id, channel_name="Niibot"),
        ]
        bot.channels.list_enabled_channels = AsyncMock(return_value=channels)
        bot.subs.remember_many = MagicMock()
        bot.subs.reconcile_all = AsyncMock(return_value={})

        enabled, results = await Bot._reconcile_enabled_subscriptions(bot)

        assert enabled == channels
        assert results == {}
        bot.subs.reconcile_all.assert_awaited_once_with(["ch1", "ch2"])

    async def test_bootstrap_only_mod_checks_converged_channels(self, bot):
        from twitch.core.bot import Bot
        from twitch.core.subscription_manager import SubscriptionReconcileResult

        channels = [
            SimpleNamespace(channel_id="ch1", channel_name="One"),
            SimpleNamespace(channel_id="ch2", channel_name="Two"),
        ]
        bot.channels.list_enabled_channels = AsyncMock(return_value=channels)
        bot.channels.warm_channel_cache = MagicMock(return_value=2)
        bot.subs.remember_many = MagicMock()
        bot.subs.reconcile_all = AsyncMock(
            return_value={
                "ch1": SubscriptionReconcileResult(channel_id="ch1", desired=10, converged=True),
                "ch2": SubscriptionReconcileResult(
                    channel_id="ch2", desired=10, errors=("HTTP 429",), converged=False
                ),
            }
        )
        bot._check_bot_mod_status = AsyncMock()
        bot._seed_and_warm_channel = AsyncMock(return_value=1)
        bot._mod_check_pending = set()

        with patch("twitch.core.bot.asyncio.sleep", new=AsyncMock()):
            await Bot._bootstrap_channels(bot)

        bot._check_bot_mod_status.assert_awaited_once_with("ch1")
        assert "ch2" not in bot._mod_check_pending

    async def test_periodic_reconcile_retries_after_transient_failure(self, bot):
        from twitch.core.bot import Bot

        bot._reconcile_enabled_subscriptions = AsyncMock(
            side_effect=[RuntimeError("database unavailable"), ([], {})]
        )
        sleep = AsyncMock(side_effect=[None, None, asyncio.CancelledError()])

        with (
            patch("twitch.core.bot.asyncio.sleep", new=sleep),
            pytest.raises(asyncio.CancelledError),
        ):
            await Bot._periodic_subscription_reconcile(bot)

        assert bot._reconcile_enabled_subscriptions.await_count == 2


# ---------------------------------------------------------------------------
# event_token_refreshed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEventTokenRefreshed:
    async def test_persists_token_and_scopes(self, bot):
        bot._pending_refresh_revisions[("u1", "new_tok")] = 7
        payload = _make_token_refreshed_payload(
            user_id="u1",
            token="new_tok",
            refresh_token="new_ref",
            scopes=["channel:bot", "channel:read:redemptions"],
        )

        await bot.event_token_refreshed(payload)

        bot.channels.rotate_token_if_revision.assert_awaited_once_with(
            "u1",
            "new_tok",
            "new_ref",
            scopes="channel:bot channel:read:redemptions",
            token_type="broadcaster",
            expected_revision=7,
        )
        assert bot._runtime_credential_revisions["u1"] == 8

    async def test_skips_when_no_user_id(self, bot):
        payload = _make_token_refreshed_payload(user_id="", token="tok", refresh_token="ref")

        await bot.event_token_refreshed(payload)

        bot.channels.rotate_token_if_revision.assert_not_awaited()

    async def test_persists_with_none_scopes_when_scopes_empty(self, bot):
        bot._pending_refresh_revisions[("u1", "tok")] = 7
        payload = _make_token_refreshed_payload(
            user_id="u1", token="tok", refresh_token="ref", scopes=[]
        )

        await bot.event_token_refreshed(payload)

        bot.channels.rotate_token_if_revision.assert_awaited_once_with(
            "u1",
            "tok",
            "ref",
            scopes=None,
            token_type="broadcaster",
            expected_revision=7,
        )

    async def test_persists_multiple_scopes_space_separated(self, bot):
        bot._pending_refresh_revisions[("u1", "tok")] = 7
        payload = _make_token_refreshed_payload(
            user_id="u1",
            token="tok",
            refresh_token="ref",
            scopes=["user:bot", "user:read:chat", "user:write:chat"],
        )

        await bot.event_token_refreshed(payload)

        _, kwargs = bot.channels.rotate_token_if_revision.call_args
        assert kwargs["scopes"] == "user:bot user:read:chat user:write:chat"

    async def test_refresh_without_a_captured_source_revision_fails_closed(self, bot):
        payload = _make_token_refreshed_payload(
            user_id="u1", token="new_tok", refresh_token="new_ref"
        )

        await bot.event_token_refreshed(payload)

        bot.channels.rotate_token_if_revision.assert_not_awaited()

    async def test_stale_refresh_cannot_overwrite_a_newer_database_revision(self, bot):
        bot._pending_refresh_revisions[("u1", "new_tok")] = 7
        bot._runtime_credential_revisions["u1"] = 7
        bot.channels.rotate_token_if_revision.return_value = False
        bot.remove_token = AsyncMock()
        with patch(
            "twitchio.client.Client.tokens",
            new_callable=PropertyMock,
            return_value={"u1": {"token": "new_tok", "refresh": "new_ref"}},
        ):
            await bot.event_token_refreshed(
                _make_token_refreshed_payload("u1", "new_tok", "new_ref")
            )

        assert "u1" not in bot._runtime_credential_revisions
        bot.remove_token.assert_awaited_once_with("u1")


# ---------------------------------------------------------------------------
# add_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAddToken:
    async def test_coordinated_helix_get_retries_429_once(self, bot):
        from twitch.core.bot import Bot

        limited = MagicMock(status_code=429, headers={"Ratelimit-Reset": "0"})
        success = MagicMock(status_code=200, headers={})
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get = AsyncMock(side_effect=[limited, success])

        with patch("twitch.core.bot.httpx.AsyncClient", return_value=client):
            response = await Bot._coordinated_helix_get(
                bot,
                "users",
                token="secret",
                token_for="user-1",
                params={"id": "user-1"},
            )

        assert response is success
        assert client.get.await_count == 2
        assert bot.egress.acquire_helix.await_count == 2
        assert bot.egress.observe_helix.call_count == 2

    async def test_coordinated_helix_post_never_retries_429(self, bot):
        from twitch.core.bot import Bot

        limited = MagicMock(status_code=429, headers={"Retry-After": "5"})
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.post = AsyncMock(return_value=limited)

        with patch("twitch.core.bot.httpx.AsyncClient", return_value=client):
            response = await Bot._coordinated_helix_post(
                bot,
                "moderation/bans",
                token="secret",
                token_for="user-1",
                params={"broadcaster_id": "channel-1"},
                json={"data": {"user_id": "viewer-1"}},
            )

        assert response is limited
        client.post.assert_awaited_once()
        bot.egress.acquire_helix.assert_awaited_once()
        assert bot.egress.acquire_helix.await_args.args == ("user:user-1",)
        bot.egress.observe_helix.assert_called_once()

    async def test_twitchio_chat_request_uses_sender_channel_and_helix_buckets(self, bot):
        request = AsyncMock(return_value={"data": [{"is_sent": True}]})
        bot._http = SimpleNamespace(request=request)
        route = SimpleNamespace(
            use_id=False,
            token_for="bot-1",
            path="chat/messages",
            json={"sender_id": "bot-1", "broadcaster_id": "channel-1"},
        )

        bot._install_twitchio_egress_coordination()
        result = await bot._http.request(route)

        assert result == {"data": [{"is_sent": True}]}
        bot.egress.acquire_chat.assert_awaited_once()
        assert bot.egress.acquire_chat.await_args.args == ("bot-1", "channel-1")
        bot.egress.acquire_helix.assert_awaited_once_with("user:bot-1")
        request.assert_awaited_once_with(route)

    async def test_chat_429_defers_sender_without_retrying_the_mutation(self, bot):
        from twitchio.exceptions import HTTPException

        limited = HTTPException(status=429, extra="limited")
        request = AsyncMock(side_effect=limited)
        bot._http = SimpleNamespace(request=request)
        bot.egress.observe_helix.return_value = 5.0
        route = SimpleNamespace(
            use_id=False,
            token_for="bot-1",
            path="chat/messages",
            json={"sender_id": "bot-1", "broadcaster_id": "channel-1"},
        )

        bot._install_twitchio_egress_coordination()
        with pytest.raises(HTTPException):
            await bot._http.request(route)

        request.assert_awaited_once_with(route)
        bot.egress.defer_chat.assert_called_once_with("bot-1", "channel-1", 5.0)

    async def test_refresh_dispatch_captures_the_source_credential_revision(self, bot):
        original_dispatch = MagicMock()
        bot._http = SimpleNamespace(_dispatch_event=original_dispatch)
        bot._runtime_credential_revisions["u1"] = 7
        payload = SimpleNamespace(access_token="new-token")

        bot._install_twitchio_refresh_revision_capture()
        bot._http._dispatch_event("u1", payload)

        assert bot._pending_refresh_revisions[("u1", "new-token")] == 7
        original_dispatch.assert_called_once_with("u1", payload)

    async def test_persists_current_token_not_stale_args(self, bot):
        """super().add_token() may refresh internally when the passed-in token is
        near expiry, firing a fire-and-forget token_refreshed event with the NEW
        pair. The override must persist whatever twitchio is now holding — not
        the stale pre-refresh args it was called with — or a race with
        event_token_refreshed()'s persist can clobber a fresh refresh_token with
        one Twitch has already rotated away."""
        resp = MagicMock(user_id="u1", scopes=["channel:bot"])
        with (
            patch("twitchio.client.Client.add_token", new=AsyncMock(return_value=resp)),
            patch(
                "twitchio.client.Client.tokens",
                new_callable=PropertyMock,
                return_value={"u1": {"token": "fresh_tok", "refresh": "fresh_ref"}},
            ),
        ):
            await bot.add_token("stale_tok", "stale_ref")

        bot.channels.upsert_token_only.assert_awaited_once_with(
            "u1", "fresh_tok", "fresh_ref", scopes="channel:bot", token_type="broadcaster"
        )

    async def test_falls_back_to_call_args_when_user_not_in_tokens_map(self, bot):
        resp = MagicMock(user_id="u1", scopes=[])
        with (
            patch("twitchio.client.Client.add_token", new=AsyncMock(return_value=resp)),
            patch("twitchio.client.Client.tokens", new_callable=PropertyMock, return_value={}),
        ):
            await bot.add_token("tok", "ref")

        bot.channels.upsert_token_only.assert_awaited_once_with(
            "u1", "tok", "ref", scopes=None, token_type="broadcaster"
        )

    async def test_runtime_reload_does_not_persist_credential_again(self, bot):
        resp = MagicMock(user_id="u1", scopes=["channel:bot"])
        with patch("twitchio.client.Client.add_token", new=AsyncMock(return_value=resp)):
            await bot.add_token("stored_tok", "stored_ref", persist=False)

        bot.channels.upsert_token_only.assert_not_awaited()

    async def test_rate_limit_is_retried_without_refreshing_or_removing_token(self, bot):
        from twitchio.exceptions import HTTPException, InvalidTokenException

        limited = InvalidTokenException(
            "limited",
            token="tok",
            refresh="ref",
            type_="token",
            original=HTTPException(status=429, extra="rate limited"),
        )
        resp = MagicMock(user_id="u1", scopes=["channel:bot"])
        validate_task = MagicMock()
        validate_task.done.side_effect = [False, True]
        bot._http = SimpleNamespace(_validate_task=validate_task)
        bot.remove_token = AsyncMock()

        with (
            patch(
                "twitchio.client.Client.add_token",
                new=AsyncMock(side_effect=[limited, resp]),
            ) as add,
            patch("twitch.core.bot.asyncio.sleep", new=AsyncMock()) as sleep,
            patch("twitchio.client.Client.tokens", new_callable=PropertyMock, return_value={}),
        ):
            result = await bot.add_token("tok", "ref", persist=False)

        assert result is resp
        assert add.await_count == 2
        assert any(call.args == (5.0,) for call in sleep.await_args_list)
        validate_task.cancel.assert_called_once()
        bot.remove_token.assert_not_awaited()

    async def test_stored_runtime_validation_uses_revision_guard_and_shared_lock(self, bot):
        resp = MagicMock(
            user_id="u1",
            client_id="test-client-id",
            scopes=["channel:bot"],
        )
        cm = MagicMock()
        validation_conn = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=validation_conn)
        cm.__aexit__ = AsyncMock(return_value=None)
        bot.channels.token_validation_lock.return_value = cm
        bot.channels.defer_token_validation = AsyncMock(return_value=True)
        bot.channels.record_token_validation = AsyncMock(return_value=True)

        with patch("twitchio.client.Client.add_token", new=AsyncMock(return_value=resp)):
            await bot.add_token(
                "tok",
                "ref",
                persist=False,
                expected_user_id="u1",
                expected_token_type="broadcaster",
                expected_revision=7,
            )

        bot.channels.token_validation_lock.assert_called_once_with("u1", "broadcaster")
        bot.channels.defer_token_validation.assert_awaited_once_with(
            "u1", "broadcaster", expected_revision=7, connection=validation_conn
        )
        bot.channels.record_token_validation.assert_awaited_once_with(
            "u1", "broadcaster", expected_revision=7, connection=validation_conn
        )
        assert bot._runtime_credential_revisions["u1"] == 7


# ---------------------------------------------------------------------------
# load_tokens — reauth notification cooldown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLoadTokens:
    @pytest.fixture()
    def load_bot(self, bot):
        bot.channels.list_tokens = AsyncMock()
        bot.add_channel_to_db = AsyncMock()

        async def _mark_reauth_required(user_id, *, expected_revision=None):
            bot._needs_reauth.add(user_id)

        bot._mark_reauth_required = AsyncMock(side_effect=_mark_reauth_required)
        return bot

    @staticmethod
    def _token(reauth_notified_at, *, requires_reauth=False):
        from shared.models.channel import Token

        return Token(
            user_id="u1",
            token="tok",
            refresh="ref",
            token_type="broadcaster",
            requires_reauth=requires_reauth,
            reauth_notified_at=reauth_notified_at,
        )

    async def test_never_notified_logs_and_marks(self, load_bot, caplog):
        load_bot.channels.list_tokens.return_value = [self._token(None)]
        user_info = MagicMock(user_id="u1", login="streamer", scopes=[])
        load_bot.add_token = AsyncMock(return_value=user_info)

        with caplog.at_level(logging.WARNING):
            await load_bot.load_tokens()

        load_bot.add_token.assert_awaited_once_with(
            "tok",
            "ref",
            persist=False,
            expected_user_id="u1",
            expected_token_type="broadcaster",
            expected_revision=1,
        )
        load_bot._mark_reauth_required.assert_awaited_once_with("u1", expected_revision=1)
        assert "u1" in load_bot._needs_reauth
        assert any("missing scopes" in r.message for r in caplog.records)

    async def test_within_cooldown_skips_notify_but_keeps_flag(self, load_bot):
        recent = datetime.now(UTC) - timedelta(hours=1)
        load_bot.channels.list_tokens.return_value = [self._token(recent, requires_reauth=True)]
        user_info = MagicMock(user_id="u1", login="streamer", scopes=[])
        load_bot.add_token = AsyncMock(return_value=user_info)

        await load_bot.load_tokens()

        load_bot._mark_reauth_required.assert_not_awaited()
        assert "u1" in load_bot._needs_reauth

    async def test_past_cooldown_notifies_again(self, load_bot):
        stale = datetime.now(UTC) - timedelta(hours=13)
        load_bot.channels.list_tokens.return_value = [self._token(stale)]
        user_info = MagicMock(user_id="u1", login="streamer", scopes=[])
        load_bot.add_token = AsyncMock(return_value=user_info)

        await load_bot.load_tokens()

        load_bot._mark_reauth_required.assert_awaited_once_with("u1", expected_revision=1)


@pytest.mark.asyncio
class TestEventSubscriptionRevoked:
    @pytest.fixture()
    def revoked_bot(self, bot):
        bot._ch = lambda cid: cid
        bot._mark_reauth_required = AsyncMock()
        token = MagicMock(credential_revision=7)
        bot.channels.get_token = AsyncMock(return_value=token)
        return bot

    async def test_authorization_revoked_flags_reauth(self, revoked_bot):
        await revoked_bot.event_subscription_revoked(_make_revoked_payload("authorization_revoked"))
        revoked_bot._mark_reauth_required.assert_awaited_once_with("ch1", expected_revision=7)

    async def test_authorization_revoked_clears_subscription_state(self, revoked_bot):
        # Without this, is_subscribed() keeps returning True for a token Twitch
        # already killed, so a later reauth's subscribe() call becomes a no-op
        # and the channel never gets its EventSub subscriptions back.
        revoked_bot.subs._subscribed = {"ch1"}
        revoked_bot.subs._sub_ids = {"ch1": ["sub-a"]}

        await revoked_bot.event_subscription_revoked(_make_revoked_payload("authorization_revoked"))

        assert not revoked_bot.subs.is_subscribed("ch1")
        assert "ch1" not in revoked_bot.subs._sub_ids

    async def test_raid_condition_key_resolves_channel(self, revoked_bot):
        payload = _make_revoked_payload(
            "authorization_revoked", condition={"to_broadcaster_user_id": "ch2"}
        )
        await revoked_bot.event_subscription_revoked(payload)
        revoked_bot._mark_reauth_required.assert_awaited_once_with("ch2", expected_revision=7)

    async def test_non_auth_reason_does_not_flag_reauth(self, revoked_bot):
        await revoked_bot.event_subscription_revoked(
            _make_revoked_payload("notification_failures_exceeded")
        )
        revoked_bot._mark_reauth_required.assert_not_awaited()

    async def test_bot_own_id_does_not_flag_reauth(self, revoked_bot):
        payload = _make_revoked_payload(
            "authorization_revoked", condition={"broadcaster_user_id": "bot-001"}
        )
        await revoked_bot.event_subscription_revoked(payload)
        revoked_bot._mark_reauth_required.assert_not_awaited()
