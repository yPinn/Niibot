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

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.eventsub_catalog import get_channel_subscriptions
from core.subscription_manager import SubscriptionManager
from shared.twitch_scopes import BOT_CORE_SCOPES, BROADCASTER_CORE_SCOPES


def _make_manager(
    needs_reauth: set[str] | None = None,
    *,
    multi_subscribe: AsyncMock | None = None,
    list_subscriptions: AsyncMock | None = None,
    sleep: AsyncMock | None = None,
    chunk_size: int = 4,
) -> SubscriptionManager:
    return SubscriptionManager(
        bot_id="bot-1",
        multi_subscribe=multi_subscribe or AsyncMock(),
        list_subscriptions=list_subscriptions or AsyncMock(return_value=[]),
        delete_subscription=AsyncMock(),
        needs_reauth=needs_reauth if needs_reauth is not None else set(),
        request_rate=float("inf"),
        chunk_size=chunk_size,
        sleep=sleep or AsyncMock(),
        retry_jitter=lambda: 0.0,
    )


def _ok(sub_id: str, subscription=None) -> SimpleNamespace:
    # MultiSubscribeSuccess.response is Twitch's raw payload: id at data[0].
    return SimpleNamespace(
        subscription=subscription,
        response={"data": [{"id": sub_id}], "total": 1},
    )


def _err(status: int, sub_type: str) -> SimpleNamespace:
    # MultiSubscribeError(subscription: SubscriptionPayload, error: HTTPException)
    subscription = next(
        (sub for sub in get_channel_subscriptions("123", "bot-1") if sub.type == sub_type),
        SimpleNamespace(
            type=sub_type,
            version="1",
            condition={"broadcaster_user_id": "123"},
        ),
    )
    return SimpleNamespace(
        subscription=subscription,
        error=SimpleNamespace(status=status),
    )


def _resp(success=(), errors=()) -> SimpleNamespace:
    return SimpleNamespace(
        success=[_ok(sid) for sid in success],
        errors=list(errors),
    )


def _ok_for(subscriptions) -> SimpleNamespace:
    return SimpleNamespace(
        success=[
            _ok(f"created-{index}-{sub.type}", sub) for index, sub in enumerate(subscriptions)
        ],
        errors=[],
    )


def _except_type(subscriptions, sub_type: str, status: int) -> SimpleNamespace:
    successes = []
    errors = []
    for index, sub in enumerate(subscriptions):
        if sub.type == sub_type:
            errors.append(SimpleNamespace(subscription=sub, error=SimpleNamespace(status=status)))
        else:
            successes.append(_ok(f"created-{index}-{sub.type}", sub))
    return SimpleNamespace(success=successes, errors=errors)


def _remote(sub, sub_id: str, *, status: str = "enabled") -> SimpleNamespace:
    return SimpleNamespace(
        id=sub_id,
        status=status,
        type=sub.type,
        version=sub.version,
        condition=dict(sub.condition),
    )


class TestSubscribe:
    pytestmark = pytest.mark.asyncio

    async def test_channel_follow_403_does_not_flag_reauth(self):
        mgr = _make_manager(
            multi_subscribe=AsyncMock(
                side_effect=lambda subscriptions: _except_type(subscriptions, "channel.follow", 403)
            )
        )
        result = await mgr.subscribe("123")
        assert "123" not in mgr._needs_reauth
        assert result.converged
        assert result.deferred == 1
        assert mgr.is_subscribed("123")

    async def test_channel_moderator_403_does_not_flag_global_reauth(self):
        emitted = False

        async def success_with_unrelated_capability_error(subscriptions):
            nonlocal emitted
            response = _ok_for(subscriptions)
            if not emitted:
                response.errors.append(_err(403, "channel.moderator.add"))
                emitted = True
            return response

        mgr = _make_manager(
            multi_subscribe=AsyncMock(side_effect=success_with_unrelated_capability_error)
        )
        result = await mgr.subscribe("123")
        assert "123" not in mgr._needs_reauth
        assert result.converged
        assert mgr.is_subscribed("123")

    async def test_409_conflicts_are_ignored(self):
        follow = next(
            sub for sub in get_channel_subscriptions("123", "bot-1") if sub.type == "channel.follow"
        )
        list_subscriptions = AsyncMock(side_effect=[[], [_remote(follow, "existing-follow")]])
        mgr = _make_manager(list_subscriptions=list_subscriptions)
        mgr._multi_subscribe.return_value = _resp(errors=[_err(409, "channel.follow")])
        result = await mgr.subscribe("123")
        assert "123" not in mgr._needs_reauth
        assert not result.converged
        assert mgr._sub_ids["123"] == ["existing-follow"]

    async def test_real_error_with_no_success_does_not_mark_subscribed(self):
        mgr = _make_manager(
            multi_subscribe=AsyncMock(
                side_effect=lambda subscriptions: _except_type(
                    subscriptions, "channel.subscribe", 400
                )
            )
        )
        result = await mgr.subscribe("123")
        assert not result.converged
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
            request_rate=float("inf"),
            sleep=AsyncMock(),
        )

        await mgr.subscribe("123")

        resolver.assert_awaited_once_with("123")
        sent = [sub for call in mgr._multi_subscribe.await_args_list for sub in call.args[0]]
        sent_types = {sub.type for sub in sent}
        assert "channel.chat.message" in sent_types
        assert "channel.cheer" not in sent_types
        assert "channel.moderator.add" not in sent_types

    async def test_concurrent_same_channel_subscribe_is_single_flight(self):
        started = asyncio.Event()
        release = asyncio.Event()

        async def delayed_subscribe(_subs):
            started.set()
            await release.wait()
            return _resp(success=["s1"])

        async def delayed_subscribe_all(subscriptions):
            await delayed_subscribe(subscriptions)
            return _ok_for(subscriptions)

        multi_subscribe = AsyncMock(side_effect=delayed_subscribe_all)
        mgr = _make_manager(multi_subscribe=multi_subscribe, chunk_size=100)

        first = asyncio.create_task(mgr.subscribe("123"))
        await started.wait()
        second = asyncio.create_task(mgr.subscribe("123"))
        await asyncio.sleep(0)

        assert multi_subscribe.await_count == 1
        release.set()
        await asyncio.gather(first, second)

        assert multi_subscribe.await_count == 1

    async def test_eventsub_mutations_are_serialized_across_channels(self):
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        active = 0
        max_active = 0

        async def delayed_subscribe(_subs):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            if not first_started.is_set():
                first_started.set()
                await release_first.wait()
            active -= 1
            return _resp(success=[f"s-{multi_subscribe.await_count}"])

        multi_subscribe = AsyncMock(side_effect=delayed_subscribe)
        mgr = _make_manager(multi_subscribe=multi_subscribe)

        first = asyncio.create_task(mgr.subscribe("123"))
        await first_started.wait()
        second = asyncio.create_task(mgr.subscribe("456"))
        await asyncio.sleep(0)

        assert multi_subscribe.await_count == 1
        release_first.set()
        await asyncio.gather(first, second)

        assert max_active == 1

    async def test_catalog_is_sent_in_bounded_chunks(self):
        multi_subscribe = AsyncMock(return_value=_resp())
        mgr = _make_manager(multi_subscribe=multi_subscribe)

        await mgr.subscribe("123")

        assert multi_subscribe.await_count > 1
        assert all(len(call.args[0]) <= 4 for call in multi_subscribe.await_args_list)

    async def test_429_retries_only_rate_limited_subscriptions(self):
        sleep = AsyncMock()
        multi_subscribe = AsyncMock(
            side_effect=[
                _resp(
                    success=["first"],
                    errors=[
                        _err(429, "channel.chat.message"),
                        _err(400, "channel.subscribe"),
                    ],
                ),
                _resp(success=["retried"]),
                _resp(),
                _resp(),
                _resp(),
            ]
        )
        mgr = _make_manager(multi_subscribe=multi_subscribe, sleep=sleep)

        await mgr.subscribe("123")

        retried = multi_subscribe.await_args_list[1].args[0]
        assert [sub.type for sub in retried] == ["channel.chat.message"]
        assert sleep.await_args_list[0].args[0] == 5.0
        assert mgr._sub_ids["123"] == ["first", "retried"]

    async def test_429_retry_is_bounded(self):
        sleep = AsyncMock()
        multi_subscribe = AsyncMock(return_value=_resp(errors=[_err(429, "stream.online")]))
        mgr = _make_manager(multi_subscribe=multi_subscribe, sleep=sleep)

        result = await mgr.subscribe("123")

        assert multi_subscribe.await_count == 4
        assert [call.args[0] for call in sleep.await_args_list] == [5.0, 10.0, 20.0]
        assert not result.converged
        assert not mgr.is_subscribed("123")


class TestDesiredStateReconciliation:
    pytestmark = pytest.mark.asyncio

    async def test_restart_adopts_existing_conduit_subscriptions_without_create(self):
        desired = get_channel_subscriptions("123", "bot-1")
        remote = [_remote(sub, f"remote-{index}") for index, sub in enumerate(desired)]
        list_subscriptions = AsyncMock(return_value=remote)
        mgr = _make_manager(list_subscriptions=list_subscriptions)

        result = await mgr.subscribe("123")

        assert result.converged
        assert result.adopted == len(desired)
        mgr._multi_subscribe.assert_not_awaited()
        assert mgr._sub_ids["123"] == [item.id for item in remote]

    async def test_creates_only_missing_desired_subscriptions(self):
        desired = get_channel_subscriptions("123", "bot-1")
        remote = [_remote(sub, f"remote-{index}") for index, sub in enumerate(desired[:-1])]
        list_subscriptions = AsyncMock(return_value=remote)
        multi_subscribe = AsyncMock(return_value=_resp(success=["created-last"]))
        mgr = _make_manager(
            list_subscriptions=list_subscriptions,
            multi_subscribe=multi_subscribe,
            chunk_size=100,
        )

        result = await mgr.subscribe("123")

        assert result.converged
        assert result.created == 1
        sent = multi_subscribe.await_args.args[0]
        assert len(sent) == 1
        assert sent[0].type == desired[-1].type
        assert sent[0].condition == desired[-1].condition

    async def test_full_reconcile_deletes_duplicate_and_obsolete_subscriptions(self):
        desired = get_channel_subscriptions("123", "bot-1")
        remote = [_remote(sub, f"remote-{index}") for index, sub in enumerate(desired)]
        remote.append(_remote(desired[0], "duplicate"))
        obsolete = SimpleNamespace(
            id="obsolete",
            status="enabled",
            type="channel.update",
            version="1",
            condition={"broadcaster_user_id": "999"},
        )
        remote.append(obsolete)
        list_subscriptions = AsyncMock(return_value=remote)
        mgr = _make_manager(list_subscriptions=list_subscriptions)

        results = await mgr.reconcile_all(["123"])

        assert results["123"].converged
        deleted = {call.args[0] for call in mgr._delete_subscription.await_args_list}
        assert deleted == {"duplicate", "obsolete"}

    async def test_remote_list_failure_is_reported_and_not_marked_subscribed(self):
        mgr = _make_manager(
            list_subscriptions=AsyncMock(side_effect=RuntimeError("provider unavailable"))
        )

        result = await mgr.subscribe("123")

        assert not result.converged
        assert result.error_count == 1
        assert not mgr.is_subscribed("123")
        mgr._multi_subscribe.assert_not_awaited()

    async def test_create_transport_failure_returns_incomplete_result(self):
        mgr = _make_manager(multi_subscribe=AsyncMock(side_effect=RuntimeError("connection reset")))

        result = await mgr.subscribe("123")

        assert not result.converged
        assert result.errors == ("create:RuntimeError",)
        assert not mgr.is_subscribed("123")

    async def test_scope_plan_failure_preserves_remote_channel_subscriptions(self):
        desired = get_channel_subscriptions("123", "bot-1")
        remote = [_remote(sub, f"remote-{index}") for index, sub in enumerate(desired)]
        mgr = SubscriptionManager(
            bot_id="bot-1",
            multi_subscribe=AsyncMock(),
            list_subscriptions=AsyncMock(return_value=remote),
            delete_subscription=AsyncMock(),
            needs_reauth=set(),
            scope_resolver=AsyncMock(side_effect=RuntimeError("database unavailable")),
            request_rate=float("inf"),
            sleep=AsyncMock(),
        )

        results = await mgr.reconcile_all(["123"])

        assert results["123"].errors == ("plan:RuntimeError",)
        mgr._delete_subscription.assert_not_awaited()

    async def test_full_reconcile_clears_stale_local_state(self):
        mgr = _make_manager()
        mgr._subscribed = {"disabled-channel"}
        mgr._sub_ids = {"disabled-channel": ["old-id"]}

        await mgr.reconcile_all([])

        assert not mgr.is_subscribed("disabled-channel")
        assert "disabled-channel" not in mgr._sub_ids


class TestResubscribeFollow:
    pytestmark = pytest.mark.asyncio

    async def test_creates_follow_sub_and_records_id(self):
        desired = get_channel_subscriptions("123", "bot-1")
        follow = next(sub for sub in desired if sub.type == "channel.follow")
        remote = [
            _remote(sub, f"existing-{index}")
            for index, sub in enumerate(desired)
            if sub.type != "channel.follow"
        ]
        mgr = _make_manager(
            list_subscriptions=AsyncMock(return_value=remote),
            multi_subscribe=AsyncMock(
                return_value=SimpleNamespace(success=[_ok("follow-sub-id", follow)], errors=[])
            ),
            chunk_size=100,
        )
        mgr._subscribed = {"123"}
        mgr._sub_ids = {"123": ["existing"]}

        await mgr.resubscribe_follow("123")

        mgr._multi_subscribe.assert_awaited_once()
        sent = mgr._multi_subscribe.await_args[0][0]
        assert len(sent) == 1
        assert sent[0].condition["moderator_user_id"] == "bot-1"
        assert "follow-sub-id" in mgr._sub_ids["123"]

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
