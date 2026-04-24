"""PG NOTIFY handlers and cache refresh mixin.

Extracted from Bot to keep bot.py under 300 lines.
Depends on attributes defined in Bot.__init__:
    self._bot_id, self._subscribed_channels, self._active_sessions, self.owner_id
    self.channels, self.command_configs, self.redemption_configs
    self.timer_configs, self.message_trigger_configs
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

import twitchio

LOGGER: logging.Logger = logging.getLogger(__name__)


class _NotifyMixin:
    # ------------------------------------------------------------------
    # PG NOTIFY handlers
    # ------------------------------------------------------------------

    async def _handle_channel_toggle(self, connection, pid, channel, payload) -> None:
        try:
            LOGGER.info(f"[NOTIFY] Received raw notification on channel '{channel}': {payload}")

            data = json.loads(payload)
            channel_id = data["channel_id"]
            enabled = data["enabled"]

            if channel_id == self._bot_id:  # type: ignore[attr-defined]
                LOGGER.debug(f"[NOTIFY] Ignoring toggle for bot's own channel: {channel_id}")
                return

            LOGGER.info(
                f"[NOTIFY] Processing channel toggle: "
                f"{channel_id} -> {'ENABLE' if enabled else 'DISABLE'}"
            )

            if enabled:
                if channel_id not in self._subscribed_channels:  # type: ignore[attr-defined]
                    await self.subscribe_channel_events(channel_id)  # type: ignore[attr-defined]
                    try:
                        await self.redemption_configs.ensure_defaults(  # type: ignore[attr-defined]
                            channel_id,
                            owner_id=self.owner_id,  # type: ignore[attr-defined]
                        )
                        count = await self.command_configs.warm_cache(channel_id)  # type: ignore[attr-defined]
                        LOGGER.info(f"[NOTIFY] Warmed cache: {count} configs for {channel_id}")
                    except Exception as e:
                        LOGGER.warning(f"[NOTIFY] Failed to warm cache for {channel_id}: {e}")
                    await self._send_welcome_message(channel_id)  # type: ignore[attr-defined]
                    LOGGER.info(f"[NOTIFY] Instantly subscribed to channel: {channel_id}")
                else:
                    LOGGER.info(f"[NOTIFY] Channel {channel_id} already subscribed, skipping")
            else:
                if channel_id in self._subscribed_channels:  # type: ignore[attr-defined]
                    await self.unsubscribe_channel_events(channel_id)  # type: ignore[attr-defined]
                    LOGGER.info(f"[NOTIFY] Instantly unsubscribed from channel: {channel_id}")
                else:
                    LOGGER.info(f"[NOTIFY] Channel {channel_id} not subscribed, skipping")

        except Exception as e:
            LOGGER.exception(f"[NOTIFY] Error handling channel toggle notification: {e}")

    async def _send_welcome_message(self, channel_id: str) -> None:
        """Send a one-line welcome message when the bot is enabled for a channel."""
        try:
            users = await self.fetch_users(ids=[channel_id])  # type: ignore[attr-defined]
            if not users:
                return
            await users[0].send_message(
                message="Niibot 已上線，準備就緒。",
                sender=self._bot_id,  # type: ignore[attr-defined]
                token_for=self._bot_id,  # type: ignore[attr-defined]
            )
            LOGGER.info(f"[NOTIFY] Welcome message sent to channel {channel_id}")
        except Exception as e:
            LOGGER.warning(f"[NOTIFY] Failed to send welcome message to {channel_id}: {e}")

    async def _handle_new_token(self, connection, pid, channel, payload) -> None:
        try:
            data = json.loads(payload)
            user_id = data["user_id"]
            LOGGER.info(f"[NOTIFY] Received new token notification for user_id: {user_id}")

            if user_id == self._bot_id:  # type: ignore[attr-defined]
                LOGGER.debug(f"[NOTIFY] Ignoring new token for bot's own account: {user_id}")
                return

            token_obj = await self.channels.get_token(user_id)  # type: ignore[attr-defined]
            if not token_obj:
                LOGGER.warning(f"[NOTIFY] Token not found for user_id: {user_id}")
                return

            try:
                user_info = await self.add_token(token_obj.token, token_obj.refresh)  # type: ignore[attr-defined]
                LOGGER.info(f"[NOTIFY] Loaded token for new user: {user_info.login} ({user_id})")

                await self.add_channel_to_db(user_id, user_info.login or "unknown")  # type: ignore[attr-defined]

                if user_id not in self._subscribed_channels:  # type: ignore[attr-defined]
                    await self.subscribe_channel_events(user_id)  # type: ignore[attr-defined]

                    try:
                        await self.redemption_configs.ensure_defaults(  # type: ignore[attr-defined]
                            user_id,
                            owner_id=self.owner_id,  # type: ignore[attr-defined]
                        )
                        count = await self.command_configs.warm_cache(user_id)  # type: ignore[attr-defined]
                        LOGGER.info(f"[NOTIFY] Warmed cache: {count} configs for {user_id}")
                    except Exception as e:
                        LOGGER.warning(f"[NOTIFY] Failed to warm cache for {user_id}: {e}")

                    try:
                        streams = await self.fetch_streams(user_ids=[user_id])  # type: ignore[attr-defined]
                        if streams:
                            stream = streams[0]
                            session_id = await self.analytics.create_session(  # type: ignore[attr-defined]
                                channel_id=user_id,
                                started_at=stream.started_at or datetime.now(UTC),
                                title=stream.title,
                                game_name=stream.game_name,
                                game_id=str(stream.game_id) if stream.game_id else None,
                            )
                            self._active_sessions[user_id] = session_id  # type: ignore[attr-defined]
                            LOGGER.info(
                                f"[NOTIFY] Created recovery session {session_id} "
                                f"for live channel {user_id}"
                            )
                    except Exception as e:
                        LOGGER.warning(f"[NOTIFY] Failed to check live status for {user_id}: {e}")

                    LOGGER.info(f"[NOTIFY] Instantly subscribed to new channel: {user_id}")

            except twitchio.exceptions.InvalidTokenException as e:
                LOGGER.warning(f"[NOTIFY] Invalid token for new user {user_id}: {e}")

        except Exception as e:
            LOGGER.exception(f"[NOTIFY] Error handling new token notification: {e}")

    async def _handle_config_change(self, connection, pid, channel, payload) -> None:
        """Reload in-memory cache for the affected channel on config writes."""
        try:
            data = json.loads(payload)
            channel_id = data.get("channel_id")
            table = data.get("table", "")
            if not channel_id or channel_id not in self._subscribed_channels:  # type: ignore[attr-defined]
                return

            LOGGER.info(f"[NOTIFY] Config change on {table} for {channel_id}, refreshing cache")
            await self._refresh_channel_cache(channel_id)  # type: ignore[attr-defined]
        except Exception as e:
            LOGGER.warning(f"[NOTIFY] Error handling config_change: {e}")

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    async def _refresh_channel_cache(self, channel_id: str) -> None:
        """Reload all config caches for a single channel from DB."""
        try:
            await self.command_configs.warm_cache(channel_id)  # type: ignore[attr-defined]
        except Exception as e:
            LOGGER.warning(f"Cache refresh (commands) failed for {channel_id}: {e}")
        try:
            from shared.repositories.channel import _channel_cache, _enabled_channels_cache

            _channel_cache.invalidate(f"channel:{channel_id}")
            _enabled_channels_cache.clear()
        except Exception as e:
            LOGGER.warning(f"Cache refresh (channel) failed for {channel_id}: {e}")
        try:
            from shared.repositories.event_config import _config_cache as _evt_cache
            from shared.repositories.event_config import _config_list_cache as _evt_list_cache

            _evt_cache.clear()
            _evt_list_cache.clear()
        except Exception as e:
            LOGGER.warning(f"Cache refresh (events) failed for {channel_id}: {e}")
        try:
            from shared.repositories.command_config import _redemption_cache

            _redemption_cache.clear()
        except Exception as e:
            LOGGER.warning(f"Cache refresh (redemptions) failed for {channel_id}: {e}")
        try:
            self.timer_configs.invalidate_cache(channel_id)  # type: ignore[attr-defined]
        except Exception as e:
            LOGGER.warning(f"Cache refresh (timers) failed for {channel_id}: {e}")
        try:
            self.message_trigger_configs.invalidate_cache(channel_id)  # type: ignore[attr-defined]
        except Exception as e:
            LOGGER.warning(f"Cache refresh (triggers) failed for {channel_id}: {e}")

    async def _periodic_cache_refresh(self) -> None:
        """Safety net: reload all config caches every 5 minutes.

        Catches any pg_notify misses (e.g. LISTEN connection dropped).
        """
        while True:
            try:
                for channel_id in list(self._subscribed_channels):  # type: ignore[attr-defined]
                    await self._refresh_channel_cache(channel_id)  # type: ignore[attr-defined]
                LOGGER.debug(
                    f"Periodic cache refresh complete for {len(self._subscribed_channels)} channels"  # type: ignore[attr-defined]
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                LOGGER.warning(f"Periodic cache refresh error: {e}")
            await asyncio.sleep(300)
