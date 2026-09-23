"""EventSub subscription ownership for the bot.

Owns the per-channel subscription state that used to live loose on ``Bot``:

- ``_subscribed``    — channel ids with a live EventSub subscription set
- ``_sub_ids``       — channel id → the subscription ids we created (for teardown)
- ``_names``         — channel id → login name, for log enrichment (``ch()``)

Constructed with callables (``multi_subscribe`` / ``delete_subscription``) rather
than the ``Bot`` itself so it can be unit-tested standalone. EventSub failures
are capability diagnostics; credential validity belongs to the authorization
service and is never inferred from one subscription response.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from twitchio import eventsub

from core.eventsub_catalog import get_channel_subscriptions
from shared.retry_utils import parse_retry_after

LOGGER: logging.Logger = logging.getLogger(__name__)

_MultiSubscribe = Callable[[list[eventsub.SubscriptionPayload]], Awaitable[Any]]
_ListSubscriptions = Callable[[], Awaitable[list[Any]]]
_DeleteSubscription = Callable[[str], Awaitable[Any]]
_ScopeResolver = Callable[[str], Awaitable[tuple[set[str], set[str], set[str]]]]
_Sleep = Callable[[float], Awaitable[None]]
_Clock = Callable[[], float]
_Jitter = Callable[[], float]

_DEFAULT_REQUEST_RATE = 5.0
_DEFAULT_CHUNK_SIZE = 4
_DEFAULT_MAX_RETRIES = 3
_BASE_RETRY_DELAY = 5.0
_MAX_RETRY_DELAY = 120.0

_SubscriptionKey = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class SubscriptionReconcileResult:
    channel_id: str
    desired: int
    adopted: int = 0
    created: int = 0
    deleted: int = 0
    deferred: int = 0
    errors: tuple[str, ...] = ()
    converged: bool = False

    @property
    def error_count(self) -> int:
        return len(self.errors)


class _NamedChannel(Protocol):
    channel_id: str
    channel_name: str | None


def _sub_id(success_item: Any) -> str | None:
    """Subscription id from a ``MultiSubscribeSuccess``: nested in Twitch's raw
    response at ``response["data"][0]["id"]``, not ``response["id"]``.
    """
    data = success_item.response.get("data") or []
    sid = data[0].get("id") if data else None
    return sid if isinstance(sid, str) else None


def _subscription_key(subscription: Any) -> _SubscriptionKey:
    condition = json.dumps(
        dict(subscription.condition),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return str(subscription.type), str(subscription.version), condition


def _belongs_to_channel(subscription: Any, channel_id: str) -> bool:
    condition = dict(subscription.condition)
    return channel_id in {
        str(condition.get("broadcaster_user_id", "")),
        str(condition.get("from_broadcaster_user_id", "")),
        str(condition.get("to_broadcaster_user_id", "")),
    }


class SubscriptionManager:
    def __init__(
        self,
        *,
        bot_id: str,
        multi_subscribe: _MultiSubscribe,
        list_subscriptions: _ListSubscriptions | None = None,
        delete_subscription: _DeleteSubscription,
        needs_reauth: set[str],
        scope_resolver: _ScopeResolver | None = None,
        request_rate: float = _DEFAULT_REQUEST_RATE,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        sleep: _Sleep = asyncio.sleep,
        monotonic: _Clock = time.monotonic,
        retry_jitter: _Jitter = random.random,
    ) -> None:
        if request_rate <= 0:
            raise ValueError("request_rate must be positive")
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")

        self._bot_id = bot_id
        self._multi_subscribe = multi_subscribe
        self._list_subscriptions = list_subscriptions or self._empty_subscription_list
        self._delete_subscription = delete_subscription
        self._needs_reauth = needs_reauth
        self._scope_resolver = scope_resolver
        self._request_rate = request_rate
        self._chunk_size = chunk_size
        self._max_retries = max_retries
        self._sleep = sleep
        self._monotonic = monotonic
        self._retry_jitter = retry_jitter

        self._subscribed: set[str] = set()
        self._sub_ids: dict[str, list[str]] = {}
        self._names: dict[str, str] = {}
        self._mutation_lock = asyncio.Lock()
        self._next_request_at = 0.0
        self._dirty_channels: set[str] = set()

    @staticmethod
    async def _empty_subscription_list() -> list[Any]:
        return []

    # ------------------------------------------------------------------
    # Name registry (log enrichment)
    # ------------------------------------------------------------------

    def ch(self, channel_id: str) -> str:
        """Return 'login(id)' when the name is known, otherwise just 'id'."""
        name = self._names.get(channel_id)
        return f"{name}({channel_id})" if name else channel_id

    def remember(self, channel_id: str, name: str) -> None:
        self._names[channel_id] = name.lower()

    def remember_many(self, channels: Iterable[_NamedChannel]) -> None:
        for ch in channels:
            if ch.channel_name:
                self._names[ch.channel_id] = ch.channel_name.lower()

    def forget(self, channel_id: str) -> None:
        self._names.pop(channel_id, None)

    @property
    def names_count(self) -> int:
        return len(self._names)

    # ------------------------------------------------------------------
    # Subscription state
    # ------------------------------------------------------------------

    @property
    def subscribed(self) -> frozenset[str]:
        return frozenset(self._subscribed)

    def is_subscribed(self, channel_id: str) -> bool:
        return channel_id in self._subscribed

    def mark_revoked(self, channel_id: str) -> None:
        """Drop local state after Twitch revokes the channel's subscriptions
        out-of-band (e.g. authorization_revoked). Without this, is_subscribed()
        keeps returning True for a token Twitch already killed, so a later
        reauth's ``if not is_subscribed(): subscribe()`` guard treats the
        channel as already subscribed and never recreates the subscriptions.
        """
        self._subscribed.discard(channel_id)
        self._sub_ids.pop(channel_id, None)

    # ------------------------------------------------------------------
    # Subscribe / unsubscribe
    # ------------------------------------------------------------------

    async def _wait_for_request_budget(self, request_count: int) -> None:
        now = self._monotonic()
        scheduled_at = max(now, self._next_request_at)
        wait_seconds = scheduled_at - now
        self._next_request_at = scheduled_at + (request_count / self._request_rate)
        if wait_seconds > 0:
            await self._sleep(wait_seconds)

    async def _subscribe_chunk(
        self, subscriptions: list[eventsub.SubscriptionPayload]
    ) -> tuple[list[Any], list[Any]]:
        successes: list[Any] = []
        errors: list[Any] = []
        pending = subscriptions

        for attempt in range(self._max_retries + 1):
            await self._wait_for_request_budget(len(pending))
            response = await self._multi_subscribe(pending)
            successes.extend(response.success)

            rate_limited = [error for error in response.errors if error.error.status == 429]
            errors.extend(error for error in response.errors if error.error.status != 429)
            if not rate_limited:
                break
            if attempt == self._max_retries:
                errors.extend(rate_limited)
                break

            fallback = _BASE_RETRY_DELAY * (2**attempt)
            delay = max(parse_retry_after(error.error, fallback=fallback) for error in rate_limited)
            delay = min(delay, _MAX_RETRY_DELAY)
            delay += max(0.0, min(self._retry_jitter(), 1.0))
            LOGGER.warning(
                "EventSub rate limited; retrying %d subscription(s) in %.1fs (%d/%d)",
                len(rate_limited),
                delay,
                attempt + 1,
                self._max_retries,
            )
            await self._sleep(delay)
            pending = [error.subscription for error in rate_limited]

        return successes, errors

    async def _subscribe_bounded(
        self, subscriptions: list[eventsub.SubscriptionPayload]
    ) -> tuple[list[Any], list[Any]]:
        successes: list[Any] = []
        errors: list[Any] = []
        for offset in range(0, len(subscriptions), self._chunk_size):
            chunk = subscriptions[offset : offset + self._chunk_size]
            chunk_successes, chunk_errors = await self._subscribe_chunk(chunk)
            successes.extend(chunk_successes)
            errors.extend(chunk_errors)
            if any(error.error.status == 429 for error in chunk_errors):
                break
        return successes, errors

    async def _desired_for_channel(self, channel_id: str) -> list[eventsub.SubscriptionPayload]:
        if self._scope_resolver is None:
            return get_channel_subscriptions(channel_id, self._bot_id)
        broadcaster_scopes, bot_scopes, enabled_capabilities = await self._scope_resolver(
            channel_id
        )
        return get_channel_subscriptions(
            channel_id,
            self._bot_id,
            broadcaster_scopes=broadcaster_scopes,
            bot_scopes=bot_scopes,
            enabled_capabilities=enabled_capabilities,
        )

    @staticmethod
    def _error_text(error: Any) -> str:
        return f"{error.subscription.type}:HTTP {error.error.status}"

    async def _delete_remote(self, subscription_id: str) -> None:
        for attempt in range(self._max_retries + 1):
            await self._wait_for_request_budget(1)
            try:
                await self._delete_subscription(subscription_id)
                return
            except Exception as exc:
                if getattr(exc, "status", None) != 429 or attempt == self._max_retries:
                    raise
                fallback = _BASE_RETRY_DELAY * (2**attempt)
                delay = min(parse_retry_after(exc, fallback=fallback), _MAX_RETRY_DELAY)
                delay += max(0.0, min(self._retry_jitter(), 1.0))
                await self._sleep(delay)

    async def _reconcile_locked(
        self,
        channel_ids: list[str],
        *,
        prune_unmatched: bool,
    ) -> dict[str, SubscriptionReconcileResult]:
        unique_ids = list(dict.fromkeys(channel_ids))
        desired_by_key: dict[_SubscriptionKey, tuple[str, eventsub.SubscriptionPayload]] = {}
        desired_keys: dict[str, set[_SubscriptionKey]] = {
            channel_id: set() for channel_id in unique_ids
        }
        plan_errors: dict[str, str] = {}
        for channel_id in unique_ids:
            try:
                desired = await self._desired_for_channel(channel_id)
            except Exception as exc:
                plan_errors[channel_id] = f"plan:{type(exc).__name__}"
                self._dirty_channels.add(channel_id)
                LOGGER.warning("[%s] EventSub plan failed: %s", self.ch(channel_id), exc)
                continue
            for subscription in desired:
                key = _subscription_key(subscription)
                desired_by_key[key] = channel_id, subscription
                desired_keys[channel_id].add(key)

        try:
            remote = [sub for sub in await self._list_subscriptions() if sub.status == "enabled"]
        except Exception as exc:
            LOGGER.warning("EventSub remote-state fetch failed: %s", exc)
            results: dict[str, SubscriptionReconcileResult] = {}
            for channel_id in unique_ids:
                self._dirty_channels.add(channel_id)
                results[channel_id] = SubscriptionReconcileResult(
                    channel_id=channel_id,
                    desired=len(desired_keys[channel_id]),
                    errors=(f"remote_list:{type(exc).__name__}",),
                )
            return results

        remote_by_key: dict[_SubscriptionKey, list[Any]] = {}
        for subscription in remote:
            remote_by_key.setdefault(_subscription_key(subscription), []).append(subscription)

        kept_remote: dict[_SubscriptionKey, Any] = {}
        delete_candidates: list[Any] = []
        target_ids = set(unique_ids)
        failed_plan_ids = set(plan_errors)
        for key, subscriptions in remote_by_key.items():
            if key in desired_by_key:
                kept_remote[key] = subscriptions[0]
                delete_candidates.extend(subscriptions[1:])
                continue
            belongs_to_target = any(
                _belongs_to_channel(subscription, channel_id)
                for subscription in subscriptions
                for channel_id in target_ids
            )
            belongs_to_failed_plan = any(
                _belongs_to_channel(subscription, channel_id)
                for subscription in subscriptions
                for channel_id in failed_plan_ids
            )
            if belongs_to_failed_plan:
                continue
            if prune_unmatched or belongs_to_target:
                delete_candidates.extend(subscriptions)

        delete_errors: list[str] = []
        deleted = 0
        for subscription in delete_candidates:
            try:
                await self._delete_remote(subscription.id)
                deleted += 1
            except Exception as exc:
                delete_errors.append(f"delete:{subscription.id}:{type(exc).__name__}")
                LOGGER.warning("Failed to delete obsolete EventSub %s: %s", subscription.id, exc)

        missing = [
            subscription
            for key, (_, subscription) in desired_by_key.items()
            if key not in kept_remote
        ]
        successes: list[Any] = []
        errors: list[Any] = []
        create_error: str | None = None
        if missing:
            try:
                successes, errors = await self._subscribe_bounded(missing)
            except Exception as exc:
                create_error = f"create:{type(exc).__name__}"
                LOGGER.warning("EventSub create request failed: %s", exc)

        created_by_key: dict[_SubscriptionKey, str] = {}
        unassigned_missing = iter(missing)
        for success in successes:
            success_subscription: Any | None = getattr(success, "subscription", None)
            if success_subscription is None:
                success_subscription = next(unassigned_missing, None)
            sid = _sub_id(success)
            if success_subscription is not None and sid is not None:
                created_by_key[_subscription_key(success_subscription)] = sid

        deferred_keys: set[_SubscriptionKey] = set()
        real_errors: list[Any] = []
        saw_conflict = False
        for error in errors:
            status = error.error.status
            if status == 409:
                saw_conflict = True
                continue
            key = _subscription_key(error.subscription)
            if status == 403 and error.subscription.type == "channel.follow":
                deferred_keys.add(key)
            else:
                real_errors.append(error)

        if saw_conflict:
            try:
                refreshed = [
                    sub for sub in await self._list_subscriptions() if sub.status == "enabled"
                ]
                for subscription in refreshed:
                    key = _subscription_key(subscription)
                    if key in desired_by_key:
                        kept_remote[key] = subscription
            except Exception as exc:
                delete_errors.append(f"conflict_refetch:{type(exc).__name__}")

        present_keys = set(kept_remote) | set(created_by_key)
        if prune_unmatched:
            stale_local = self._subscribed - target_ids
            self._subscribed.difference_update(stale_local)
            self._dirty_channels.difference_update(stale_local)
            for channel_id in stale_local:
                self._sub_ids.pop(channel_id, None)
        results = {}
        for channel_id in unique_ids:
            channel_desired = desired_keys[channel_id]
            channel_deferred = channel_desired & deferred_keys
            channel_errors = [
                self._error_text(error)
                for error in real_errors
                if _subscription_key(error.subscription) in channel_desired
            ]
            channel_errors.extend(delete_errors)
            if channel_id in plan_errors:
                channel_errors.append(plan_errors[channel_id])
            if create_error and channel_desired - set(kept_remote):
                channel_errors.append(create_error)
            required = channel_desired - channel_deferred
            converged = required.issubset(present_keys) and not channel_errors
            ids = [
                subscription.id
                for key, subscription in kept_remote.items()
                if key in channel_desired
            ]
            ids.extend(
                sid
                for key, sid in created_by_key.items()
                if key in channel_desired and sid not in ids
            )
            if ids:
                self._sub_ids[channel_id] = ids
            else:
                self._sub_ids.pop(channel_id, None)

            if converged:
                self._subscribed.add(channel_id)
                self._dirty_channels.discard(channel_id)
                LOGGER.info("[%s] EventSub desired state converged", self.ch(channel_id))
            else:
                self._subscribed.discard(channel_id)
                self._dirty_channels.add(channel_id)
                LOGGER.warning(
                    "[%s] EventSub desired state incomplete: present=%d desired=%d errors=%s",
                    self.ch(channel_id),
                    len(channel_desired & present_keys),
                    len(channel_desired),
                    channel_errors,
                )

            results[channel_id] = SubscriptionReconcileResult(
                channel_id=channel_id,
                desired=len(channel_desired),
                adopted=len(channel_desired & set(kept_remote)),
                created=len(channel_desired & set(created_by_key)),
                deleted=deleted,
                deferred=len(channel_deferred),
                errors=tuple(channel_errors),
                converged=converged,
            )
        return results

    async def reconcile_all(
        self, channel_ids: Iterable[str]
    ) -> dict[str, SubscriptionReconcileResult]:
        async with self._mutation_lock:
            return await self._reconcile_locked(list(channel_ids), prune_unmatched=True)

    async def subscribe(self, channel_id: str) -> SubscriptionReconcileResult:
        async with self._mutation_lock:
            if channel_id in self._subscribed and channel_id not in self._dirty_channels:
                LOGGER.debug("[%s] Already subscribed, skipping", self.ch(channel_id))
                count = len(self._sub_ids.get(channel_id, ()))
                return SubscriptionReconcileResult(
                    channel_id=channel_id,
                    desired=count,
                    adopted=count,
                    converged=True,
                )
            return (await self._reconcile_locked([channel_id], prune_unmatched=False))[channel_id]

    async def resubscribe_follow(self, channel_id: str) -> None:
        """(Re)create the channel.follow subscription once the bot is a mod."""
        async with self._mutation_lock:
            if channel_id not in self._subscribed:
                return
            self._dirty_channels.add(channel_id)
            await self._reconcile_locked([channel_id], prune_unmatched=False)

    async def unsubscribe(self, channel_id: str) -> None:
        async with self._mutation_lock:
            try:
                sub_ids = set(self._sub_ids.get(channel_id, []))
                try:
                    remote = await self._list_subscriptions()
                    sub_ids.update(
                        subscription.id
                        for subscription in remote
                        if subscription.status == "enabled"
                        and _belongs_to_channel(subscription, channel_id)
                    )
                except Exception as exc:
                    LOGGER.warning(
                        "[%s] Could not list remote subscriptions during unsubscribe: %s",
                        self.ch(channel_id),
                        exc,
                    )
                if sub_ids:
                    for sub_id in sub_ids:
                        try:
                            await self._delete_remote(sub_id)
                            LOGGER.debug(f"[{self.ch(channel_id)}] Deleted subscription {sub_id}")
                        except Exception as e:
                            LOGGER.warning(
                                f"[{self.ch(channel_id)}] Failed to delete subscription {sub_id}: {e}"
                            )
                    self._sub_ids.pop(channel_id, None)
                else:
                    LOGGER.debug(f"[{self.ch(channel_id)}] No subscription IDs found")

                self._subscribed.discard(channel_id)
                self._dirty_channels.discard(channel_id)
                LOGGER.info(f"[{self.ch(channel_id)}] Unsubscribed from events")

            except Exception as e:
                LOGGER.exception(f"[{self.ch(channel_id)}] Failed to unsubscribe: {e}")
