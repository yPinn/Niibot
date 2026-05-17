"""Channel management mixin — DB channel CRUD and EventSub subscriptions.

Extracted from Bot to keep bot.py under 300 lines.
Depends on attributes defined in Bot.__init__:
    self._bot_id, self._subscribed_channels, self._subscription_ids
    self._channel_names, self.channels, self.command_configs, self.redemption_configs, self.owner_id
"""

from __future__ import annotations

import logging

from core.subscriptions import get_channel_subscriptions

LOGGER: logging.Logger = logging.getLogger(__name__)


class _ChannelMixin:
    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ch(self, channel_id: str) -> str:
        """Return 'login(id)' when name is known, otherwise just 'id'."""
        name = self._channel_names.get(channel_id)  # type: ignore[attr-defined]
        return f"{name}({channel_id})" if name else channel_id

    # ------------------------------------------------------------------
    # Channel management
    # ------------------------------------------------------------------

    async def load_channels(self) -> list[str]:
        enabled = await self.channels.list_enabled_channels()  # type: ignore[attr-defined]
        names = [ch.channel_name for ch in enabled]
        LOGGER.info(f"Loaded {len(names)} channels from database")
        return names

    async def add_channel_to_db(self, channel_id: str, channel_name: str) -> None:
        if channel_id == self._bot_id:  # type: ignore[attr-defined]
            LOGGER.debug(f"Skipping bot's own channel: {channel_name}")
            return

        await self.channels.upsert_channel(channel_id, channel_name.lower(), enabled=True)  # type: ignore[attr-defined]
        self._channel_names[channel_id] = channel_name.lower()  # type: ignore[attr-defined]
        LOGGER.info(f"Added channel {channel_name} (ID: {channel_id}) to database")

    async def remove_channel_from_db(self, channel_name: str) -> None:
        await self.channels.disable_channel_by_name(channel_name.lower())  # type: ignore[attr-defined]
        LOGGER.info(f"Disabled channel {channel_name} in database")

    async def subscribe_channel_events(self, broadcaster_user_id: str) -> None:
        if broadcaster_user_id in self._subscribed_channels:  # type: ignore[attr-defined]
            LOGGER.debug(f"[{self._ch(broadcaster_user_id)}] Already subscribed, skipping")
            return

        try:
            subs = get_channel_subscriptions(broadcaster_user_id, self._bot_id)  # type: ignore[attr-defined]
            resp = await self.multi_subscribe(subs)  # type: ignore[attr-defined]
            non_conflict: list = []
            follow_auth_errors: list = []
            if resp.errors:
                for e in resp.errors:
                    e_str = str(e)
                    if "409" in e_str or "already exists" in e_str:
                        continue
                    elif "403" in e_str and (
                        "ChannelFollow" in e_str or "ChannelModerator" in e_str
                    ):
                        # broadcaster missing required scope:
                        #   ChannelFollow      → moderator:read:followers
                        #   ChannelModerator   → moderation:read / channel:manage:moderators
                        follow_auth_errors.append(e)
                    else:
                        non_conflict.append(e)
                if non_conflict:
                    LOGGER.warning(
                        f"[{self._ch(broadcaster_user_id)}] Subscription errors: {non_conflict}"
                    )
                if follow_auth_errors:
                    LOGGER.warning(
                        f"[{self._ch(broadcaster_user_id)}] Auth-scope subscription failures"
                        " — broadcaster needs to reauth (moderator:read:followers,"
                        " moderation:read / channel:manage:moderators)"
                    )
                    self._needs_reauth.add(broadcaster_user_id)  # type: ignore[attr-defined]

            subscription_ids: list[str] = []
            for success_item in resp.success:
                sub_id = success_item.response.get("id")
                if sub_id and isinstance(sub_id, str):
                    subscription_ids.append(sub_id)

            if subscription_ids:
                self._subscription_ids[broadcaster_user_id] = subscription_ids  # type: ignore[attr-defined]

            # Mark as subscribed unless there are real (non-409, non-follow-403) errors with no
            # successes. follow_auth_errors only means channel.follow is unavailable until reauth —
            # the other subscriptions still exist on the Conduit from the previous session.
            if subscription_ids or not non_conflict:
                self._subscribed_channels.add(broadcaster_user_id)  # type: ignore[attr-defined]
                LOGGER.info(f"[{self._ch(broadcaster_user_id)}] Subscribed to events")
            else:
                LOGGER.warning(
                    f"[{self._ch(broadcaster_user_id)}] Subscription failed: {non_conflict}"
                )

        except Exception as e:
            LOGGER.exception(f"[{self._ch(broadcaster_user_id)}] Failed to subscribe: {e}")

    async def unsubscribe_channel_events(self, broadcaster_user_id: str) -> None:
        if broadcaster_user_id not in self._subscribed_channels:  # type: ignore[attr-defined]
            LOGGER.debug(f"[{self._ch(broadcaster_user_id)}] Not subscribed, skipping")
            return

        try:
            subscription_ids = self._subscription_ids.get(broadcaster_user_id, [])  # type: ignore[attr-defined]

            if subscription_ids:
                for sub_id in subscription_ids:
                    try:
                        await self.delete_eventsub_subscription(sub_id)  # type: ignore[attr-defined]
                        LOGGER.debug(
                            f"[{self._ch(broadcaster_user_id)}] Deleted subscription {sub_id}"
                        )
                    except Exception as e:
                        LOGGER.warning(
                            f"[{self._ch(broadcaster_user_id)}] Failed to delete subscription {sub_id}: {e}"
                        )

                del self._subscription_ids[broadcaster_user_id]  # type: ignore[attr-defined]
            else:
                LOGGER.warning(f"[{self._ch(broadcaster_user_id)}] No subscription IDs found")

            self._subscribed_channels.discard(broadcaster_user_id)  # type: ignore[attr-defined]
            LOGGER.info(f"[{self._ch(broadcaster_user_id)}] Unsubscribed from events")

        except Exception as e:
            LOGGER.exception(f"[{self._ch(broadcaster_user_id)}] Failed to unsubscribe: {e}")
