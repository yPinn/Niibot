"""Channel management mixin — DB channel CRUD and EventSub subscriptions.

Extracted from Bot to keep bot.py under 300 lines.
Depends on attributes defined in Bot.__init__:
    self._bot_id, self._subscribed_channels, self._subscription_ids
    self.channels, self.command_configs, self.redemption_configs, self.owner_id
"""

from __future__ import annotations

import logging

from core.subscriptions import get_channel_subscriptions

LOGGER: logging.Logger = logging.getLogger(__name__)


class _ChannelMixin:
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
        LOGGER.info(f"Added channel {channel_name} (ID: {channel_id}) to database")

    async def remove_channel_from_db(self, channel_name: str) -> None:
        await self.channels.disable_channel_by_name(channel_name.lower())  # type: ignore[attr-defined]
        LOGGER.info(f"Disabled channel {channel_name} in database")

    async def subscribe_channel_events(self, broadcaster_user_id: str) -> None:
        if broadcaster_user_id in self._subscribed_channels:  # type: ignore[attr-defined]
            LOGGER.debug(f"Already subscribed: {broadcaster_user_id}")
            return

        try:
            subs = get_channel_subscriptions(broadcaster_user_id, self._bot_id)  # type: ignore[attr-defined]
            resp = await self.multi_subscribe(subs)  # type: ignore[attr-defined]
            if resp.errors:
                non_conflict = [
                    e for e in resp.errors if "409" not in str(e) and "already exists" not in str(e)
                ]
                if non_conflict:
                    LOGGER.warning(f"Subscription errors: {non_conflict}")

            subscription_ids: list[str] = []
            for success_item in resp.success:
                sub_id = success_item.response.get("id")
                if sub_id and isinstance(sub_id, str):
                    subscription_ids.append(sub_id)

            if subscription_ids:
                self._subscription_ids[broadcaster_user_id] = subscription_ids  # type: ignore[attr-defined]

            self._subscribed_channels.add(broadcaster_user_id)  # type: ignore[attr-defined]
            LOGGER.info(f"Subscribed to events for channel: {broadcaster_user_id}")

        except Exception as e:
            LOGGER.exception(f"Failed to subscribe channel {broadcaster_user_id}: {e}")

    async def unsubscribe_channel_events(self, broadcaster_user_id: str) -> None:
        if broadcaster_user_id not in self._subscribed_channels:  # type: ignore[attr-defined]
            LOGGER.debug(f"Not subscribed to channel: {broadcaster_user_id}")
            return

        try:
            subscription_ids = self._subscription_ids.get(broadcaster_user_id, [])  # type: ignore[attr-defined]

            if subscription_ids:
                for sub_id in subscription_ids:
                    try:
                        await self.delete_eventsub_subscription(sub_id)  # type: ignore[attr-defined]
                        LOGGER.debug(
                            f"Deleted subscription {sub_id} for channel {broadcaster_user_id}"
                        )
                    except Exception as e:
                        LOGGER.warning(f"Failed to delete subscription {sub_id}: {e}")

                del self._subscription_ids[broadcaster_user_id]  # type: ignore[attr-defined]
            else:
                LOGGER.warning(f"No subscription IDs found for channel {broadcaster_user_id}")

            self._subscribed_channels.discard(broadcaster_user_id)  # type: ignore[attr-defined]
            LOGGER.info(f"Unsubscribed from events for channel: {broadcaster_user_id}")

        except Exception as e:
            LOGGER.exception(f"Failed to unsubscribe channel {broadcaster_user_id}: {e}")
