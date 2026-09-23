"""Tests for SubscriptionManager.

Focus areas (master-slave scope migration):
- channel.follow uses moderator_user_id=bot, so a 403 at subscribe time means
  "bot not mod yet" — it must NOT flag the broadcaster for reauth.
- EventSub subscription failures never declare a credential globally invalid;
  capability health is reconciled by the authorization service.
- resubscribe_follow (re)creates the follow sub once the bot is granted mod.
- Error classification is by typed HTTPException.status / subscription.type,
  not brittle string matching.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.subscription_manager import SubscriptionManager
from shared.twitch_scopes import BOT_CORE_SCOPES, BROADCASTER_CORE_SCOPES


def _make_manager(needs_reauth: set[str] | None = None) -> SubscriptionManager:
    return SubscriptionManager(
        bot_id="bot-1",
        multi_subscribe=AsyncMock(),
        delete_subscription=AsyncMock(),
        needs_reauth=needs_reauth if needs_reauth is not None else set(),
    )


def _ok(sub_id: str) -> SimpleNamespace:
    # MultiSubscribeSuccess.response is Twitch's raw payload: id at data[0].
    return SimpleNamespace(response={"data": [{"id": sub_id}], "total": 1})


def _err(status: int, sub_type: str) -> SimpleNamespace:
    # MultiSubscribeError(subscription: SubscriptionPayload, error: HTTPException)
    return SimpleNamespace(
        subscription=SimpleNamespace(type=sub_type),
        error=SimpleNamespace(status=status),
    )


def _resp(success=(), errors=()) -> SimpleNamespace:
    return SimpleNamespace(
        success=[_ok(sid) for sid in success],
        errors=list(errors),
    )


class TestSubscribe:
    pytestmark = pytest.mark.asyncio

    async def test_channel_follow_403_does_not_flag_reauth(self):
        mgr = _make_manager()
        mgr._multi_subscribe.return_value = _resp(
            success=["s1"],
            errors=[_err(403, "channel.follow")],
        )
        await mgr.subscribe("123")
        assert "123" not in mgr._needs_reauth
        assert mgr.is_subscribed("123")

    async def test_channel_moderator_403_does_not_flag_global_reauth(self):
        mgr = _make_manager()
        mgr._multi_subscribe.return_value = _resp(
            success=["s1"],
            errors=[_err(403, "channel.moderator.add")],
        )
        await mgr.subscribe("123")
        assert "123" not in mgr._needs_reauth
        assert mgr.is_subscribed("123")

    async def test_409_conflicts_are_ignored(self):
        mgr = _make_manager()
        mgr._multi_subscribe.return_value = _resp(errors=[_err(409, "channel.follow")])
        await mgr.subscribe("123")
        assert "123" not in mgr._needs_reauth
        assert mgr.is_subscribed("123")

    async def test_real_error_with_no_success_does_not_mark_subscribed(self):
        mgr = _make_manager()
        mgr._multi_subscribe.return_value = _resp(errors=[_err(400, "channel.subscribe")])
        await mgr.subscribe("123")
        assert not mgr.is_subscribed("123")

    async def test_records_subscription_ids(self):
        mgr = _make_manager()
        mgr._multi_subscribe.return_value = _resp(success=["a", "b"])
        await mgr.subscribe("123")
        assert mgr._sub_ids["123"] == ["a", "b"]

    async def test_skips_when_already_subscribed(self):
        mgr = _make_manager()
        mgr._subscribed = {"123"}
        await mgr.subscribe("123")
        mgr._multi_subscribe.assert_not_awaited()

    async def test_runtime_scope_resolver_filters_subscription_plan(self):
        resolver = AsyncMock(
            return_value=(
                set(BROADCASTER_CORE_SCOPES),
                set(BOT_CORE_SCOPES),
                set(),
            )
        )
        mgr = SubscriptionManager(
            bot_id="bot-1",
            multi_subscribe=AsyncMock(return_value=_resp(success=["s1"])),
            delete_subscription=AsyncMock(),
            needs_reauth=set(),
            scope_resolver=resolver,
        )

        await mgr.subscribe("123")

        resolver.assert_awaited_once_with("123")
        sent = mgr._multi_subscribe.await_args.args[0]
        sent_types = {sub.type for sub in sent}
        assert "channel.chat.message" in sent_types
        assert "channel.cheer" not in sent_types
        assert "channel.moderator.add" not in sent_types


class TestResubscribeFollow:
    pytestmark = pytest.mark.asyncio

    async def test_creates_follow_sub_and_records_id(self):
        mgr = _make_manager()
        mgr._subscribed = {"123"}
        mgr._sub_ids = {"123": ["existing"]}
        mgr._multi_subscribe.return_value = _resp(success=["follow-sub-id"])

        await mgr.resubscribe_follow("123")

        mgr._multi_subscribe.assert_awaited_once()
        sent = mgr._multi_subscribe.await_args[0][0]
        assert len(sent) == 1
        assert sent[0].condition["moderator_user_id"] == "bot-1"
        assert mgr._sub_ids["123"] == ["existing", "follow-sub-id"]

    async def test_409_is_treated_as_success_noop(self):
        mgr = _make_manager()
        mgr._subscribed = {"123"}
        mgr._multi_subscribe.return_value = _resp(errors=[_err(409, "channel.follow")])

        await mgr.resubscribe_follow("123")

        assert mgr._sub_ids.get("123") is None

    async def test_skips_when_channel_not_subscribed(self):
        mgr = _make_manager()
        await mgr.resubscribe_follow("123")
        mgr._multi_subscribe.assert_not_awaited()


class TestUnsubscribe:
    pytestmark = pytest.mark.asyncio

    async def test_deletes_recorded_ids(self):
        mgr = _make_manager()
        mgr._subscribed = {"123"}
        mgr._sub_ids = {"123": ["a", "b"]}

        await mgr.unsubscribe("123")

        assert mgr._delete_subscription.await_count == 2
        assert not mgr.is_subscribed("123")
        assert "123" not in mgr._sub_ids

    async def test_skips_when_not_subscribed(self):
        mgr = _make_manager()
        await mgr.unsubscribe("123")
        mgr._delete_subscription.assert_not_awaited()


class TestMarkRevoked:
    def test_clears_subscribed_state_without_calling_twitch(self):
        mgr = _make_manager()
        mgr._subscribed = {"123"}
        mgr._sub_ids = {"123": ["a", "b"]}

        mgr.mark_revoked("123")

        assert not mgr.is_subscribed("123")
        assert "123" not in mgr._sub_ids
        mgr._delete_subscription.assert_not_awaited()

    def test_noop_when_not_subscribed(self):
        mgr = _make_manager()
        mgr.mark_revoked("999")
        assert not mgr.is_subscribed("999")


class TestNameRegistry:
    def test_ch_formats_known_and_unknown(self):
        mgr = _make_manager()
        mgr.remember("123", "StreamerA")
        assert mgr.ch("123") == "streamera(123)"
        assert mgr.ch("999") == "999"

    def test_remember_many(self):
        mgr = _make_manager()
        mgr.remember_many(
            [
                SimpleNamespace(channel_id="1", channel_name="Foo"),
                SimpleNamespace(channel_id="2", channel_name=None),
            ]
        )
        assert mgr.ch("1") == "foo(1)"
        assert mgr.ch("2") == "2"
