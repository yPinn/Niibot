"""EventSub subscription ownership for the bot.

Owns the per-channel subscription state that used to live loose on ``Bot``:

- ``_subscribed``    — channel ids with a live EventSub subscription set
- ``_sub_ids``       — channel id → the subscription ids we created (for teardown)
- ``_names``         — channel id → login name, for log enrichment (``ch()``)

Constructed with callables (``multi_subscribe`` / ``delete_subscription``) rather
than the ``Bot`` itself so it can be unit-tested standalone. ``needs_reauth`` is
the set **owned by Bot** — this manager only flags into it when a broadcaster is
missing ``channel:manage:moderators`` (in-memory only, matching prior behaviour;
persisting that flag stays a Bot concern).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, Protocol

from twitchio import eventsub

from core.subscriptions import get_channel_subscriptions

LOGGER: logging.Logger = logging.getLogger(__name__)

_MultiSubscribe = Callable[[list[eventsub.SubscriptionPayload]], Awaitable[Any]]
_DeleteSubscription = Callable[[str], Awaitable[Any]]


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


class SubscriptionManager:
    def __init__(
        self,
        *,
        bot_id: str,
        multi_subscribe: _MultiSubscribe,
        delete_subscription: _DeleteSubscription,
        needs_reauth: set[str],
    ) -> None:
        self._bot_id = bot_id
        self._multi_subscribe = multi_subscribe
        self._delete_subscription = delete_subscription
        self._needs_reauth = needs_reauth

        self._subscribed: set[str] = set()
        self._sub_ids: dict[str, list[str]] = {}
        self._names: dict[str, str] = {}

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

    # ------------------------------------------------------------------
    # Subscription state
    # ------------------------------------------------------------------

    @property
    def subscribed(self) -> frozenset[str]:
        return frozenset(self._subscribed)

    def is_subscribed(self, channel_id: str) -> bool:
        return channel_id in self._subscribed

    # ------------------------------------------------------------------
    # Subscribe / unsubscribe
    # ------------------------------------------------------------------

    async def subscribe(self, channel_id: str) -> None:
        if channel_id in self._subscribed:
            LOGGER.debug(f"[{self.ch(channel_id)}] Already subscribed, skipping")
            return

        try:
            subs = get_channel_subscriptions(channel_id, self._bot_id)
            resp = await self._multi_subscribe(subs)

            real_errors: list = []
            follow_pending = False
            moderator_reauth = False
            for err in resp.errors:
                status = err.error.status
                sub_type = err.subscription.type
                if status == 409:
                    continue  # already exists — treat as success
                if status == 403 and sub_type == "channel.follow":
                    # channel.follow uses moderator_user_id=bot; a 403 means the
                    # bot is not a mod yet. resubscribe_follow() retries once mod
                    # is granted — NOT a broadcaster reauth condition.
                    follow_pending = True
                elif status == 403 and sub_type.startswith("channel.moderator"):
                    moderator_reauth = True
                else:
                    real_errors.append(err)

            if real_errors:
                LOGGER.warning(f"[{self.ch(channel_id)}] Subscription errors: {real_errors}")
            if follow_pending:
                LOGGER.debug(
                    f"[{self.ch(channel_id)}] channel.follow deferred"
                    " — bot not mod yet; will subscribe on mod grant"
                )
            if moderator_reauth:
                LOGGER.warning(
                    f"[{self.ch(channel_id)}] channel.moderator subscription"
                    " failed — broadcaster needs to reauth (channel:manage:moderators)"
                )
                self._needs_reauth.add(channel_id)

            sub_ids = [sid for s in resp.success if (sid := _sub_id(s)) is not None]
            if sub_ids:
                self._sub_ids[channel_id] = sub_ids

            # Mark subscribed unless there are real (non-409, non-follow-403) errors
            # with no successes. follow_pending / moderator_reauth don't block the
            # channel — the other subscriptions still exist on the Conduit.
            if sub_ids or not real_errors:
                self._subscribed.add(channel_id)
                LOGGER.info(f"[{self.ch(channel_id)}] Subscribed to events")
            else:
                LOGGER.warning(f"[{self.ch(channel_id)}] Subscription failed: {real_errors}")

        except Exception as e:
            LOGGER.exception(f"[{self.ch(channel_id)}] Failed to subscribe: {e}")

    async def resubscribe_follow(self, channel_id: str) -> None:
        """(Re)create the channel.follow subscription once the bot is a mod.

        channel.follow uses moderator_user_id=bot, so it 403s when attempted
        before the bot is granted mod. Called after mod is confirmed. Idempotent
        — a pre-existing subscription returns 409, treated as success.
        """
        if channel_id not in self._subscribed:
            return
        try:
            sub = eventsub.ChannelFollowSubscription(
                broadcaster_user_id=channel_id,
                moderator_user_id=self._bot_id,
            )
            resp = await self._multi_subscribe([sub])
            for err in resp.errors:
                if err.error.status == 409:
                    LOGGER.debug(f"[{self.ch(channel_id)}] channel.follow already active")
                else:
                    LOGGER.warning(
                        f"[{self.ch(channel_id)}] channel.follow re-subscribe failed: {err.error}"
                    )
                return

            new_ids = [sid for s in resp.success if (sid := _sub_id(s)) is not None]
            if new_ids:
                self._sub_ids.setdefault(channel_id, []).extend(new_ids)
                LOGGER.info(f"[{self.ch(channel_id)}] channel.follow subscribed (bot now mod)")
        except Exception as e:
            LOGGER.warning(f"[{self.ch(channel_id)}] channel.follow re-subscribe error: {e}")

    async def unsubscribe(self, channel_id: str) -> None:
        if channel_id not in self._subscribed:
            LOGGER.debug(f"[{self.ch(channel_id)}] Not subscribed, skipping")
            return

        try:
            sub_ids = self._sub_ids.get(channel_id, [])
            if sub_ids:
                for sub_id in sub_ids:
                    try:
                        await self._delete_subscription(sub_id)
                        LOGGER.debug(f"[{self.ch(channel_id)}] Deleted subscription {sub_id}")
                    except Exception as e:
                        LOGGER.warning(
                            f"[{self.ch(channel_id)}] Failed to delete subscription {sub_id}: {e}"
                        )
                del self._sub_ids[channel_id]
            else:
                LOGGER.warning(f"[{self.ch(channel_id)}] No subscription IDs found")

            self._subscribed.discard(channel_id)
            LOGGER.info(f"[{self.ch(channel_id)}] Unsubscribed from events")

        except Exception as e:
            LOGGER.exception(f"[{self.ch(channel_id)}] Failed to unsubscribe: {e}")
