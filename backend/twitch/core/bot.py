"""Twitch Bot class — core lifecycle, event handling, and channel management."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

import asyncpg
import twitchio
from twitchio import eventsub
from twitchio.ext import commands

from core.config import COMPONENTS_DIR
from core.guards import has_role, is_on_cooldown, record_cooldown
from core.pg_listener import pg_listen
from core.subscriptions import get_channel_subscriptions
from shared.repositories.analytics import AnalyticsRepository
from shared.repositories.channel import ChannelRepository
from shared.repositories.command_config import (
    CommandConfigRepository,
    RedemptionConfigRepository,
)

LOGGER: logging.Logger = logging.getLogger("Bot")


class Bot(commands.AutoBot):
    token_database: asyncpg.Pool

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        bot_id: str,
        owner_id: str,
        conduit_id: str | None,
        token_database: asyncpg.Pool,
        subs: list[eventsub.SubscriptionPayload],
    ) -> None:
        self.token_database = token_database
        self._subscribed_channels: set[str] = set()
        self._subscription_ids: dict[str, list[str]] = {}
        self._bot_id = bot_id

        self.channels = ChannelRepository(token_database)
        self.analytics = AnalyticsRepository(token_database)
        self.command_configs = CommandConfigRepository(token_database)
        self.redemption_configs = RedemptionConfigRepository(token_database)
        self._active_sessions: dict[str, int] = {}
        # In-memory chatter buffers: {channel_id: {user_id: {"username": str, "count": int, "last_at": datetime}}}
        self._chatter_buffers: dict[str, dict[str, dict]] = {}

        init_kwargs: dict = dict(
            client_id=client_id,
            client_secret=client_secret,
            bot_id=bot_id,
            owner_id=owner_id,
            prefix="!",
            subscriptions=subs,
            force_subscribe=True,
        )
        if conduit_id:
            init_kwargs["conduit_id"] = conduit_id

        super().__init__(**init_kwargs)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    async def setup_hook(self) -> None:
        if COMPONENTS_DIR.exists():
            for file in COMPONENTS_DIR.glob("*.py"):
                if file.stem == "__init__":
                    continue
                module_name = f"components.{file.stem}"
                try:
                    await self.load_module(module_name)
                except Exception as e:
                    print(f"Failed to load component {module_name}: {e}")

        asyncio.create_task(self._subscribe_initial_channels())
        asyncio.create_task(pg_listen(self.token_database, "new_token", self._handle_new_token))
        asyncio.create_task(
            pg_listen(self.token_database, "channel_toggle", self._handle_channel_toggle)
        )
        asyncio.create_task(self._recover_active_sessions())

    async def setup_database(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def event_ready(self) -> None:
        LOGGER.info("Successfully logged in as: %s", self.bot_id)

    async def event_eventsub_notification(self, payload) -> None:
        LOGGER.debug(f"EventSub notification received: {type(payload).__name__}")

    async def event_eventsub_ready(self) -> None:
        LOGGER.info("EventSub is ready to receive notifications")

    async def event_eventsub_error(self, error: Exception) -> None:
        LOGGER.error(f"EventSub error: {error}")

    async def event_oauth_authorized(
        self, payload: twitchio.authentication.UserTokenPayload
    ) -> None:
        await self.add_token(payload.access_token, payload.refresh_token)

        if not payload.user_id:
            return

        if payload.user_id == self.bot_id:
            LOGGER.info("Bot account authorized")
            return

        users = await self.fetch_users(ids=[payload.user_id])
        if users:
            user = users[0]
            if user.name:
                await self.add_channel_to_db(user.id, user.name)

            if payload.user_id == self.owner_id:
                LOGGER.info(f"Owner channel authorized and added: {user.name} (ID: {user.id})")
            else:
                LOGGER.info(f"Channel authorized and added: {user.name} (ID: {user.id})")

        if payload.user_id not in self._subscribed_channels:
            await self.subscribe_channel_events(payload.user_id)
        else:
            LOGGER.debug(f"Channel {payload.user_id} already subscribed, skipping")

    async def event_message(self, payload: twitchio.ChatMessage) -> None:
        if payload.broadcaster:
            LOGGER.debug(f"[{payload.chatter.name}#{payload.broadcaster.name}]: {payload.text}")

            if payload.broadcaster.id not in self._subscribed_channels:
                LOGGER.debug(
                    f"[BLOCK] Ignoring message from unsubscribed channel: {payload.broadcaster.name}"
                )
                return

            # Track chatter message count in-memory (only during active sessions)
            channel_id = payload.broadcaster.id
            chatter_id = payload.chatter.id
            if chatter_id != self.bot_id and channel_id in self._active_sessions:
                buf = self._chatter_buffers.setdefault(channel_id, {})
                if chatter_id in buf:
                    buf[chatter_id]["count"] += 1
                    buf[chatter_id]["last_at"] = datetime.now()
                    buf[chatter_id]["username"] = payload.chatter.name
                else:
                    buf[chatter_id] = {
                        "username": payload.chatter.name,
                        "count": 1,
                        "last_at": datetime.now(),
                    }

            # Custom command handling: text response or redirect
            await self._handle_custom_command(payload)
        else:
            LOGGER.debug(f"[{payload.chatter.name}]: {payload.text}")

        await super().event_message(payload)

    # ------------------------------------------------------------------
    # Custom command handling
    # ------------------------------------------------------------------

    async def _handle_custom_command(self, payload: twitchio.ChatMessage) -> None:
        """Handle custom commands: direct text response or redirect to builtin command."""
        text = payload.text
        if not text or not text.startswith("!"):
            return

        parts = text[1:].split(maxsplit=1)
        if not parts or not parts[0]:
            return

        cmd_name = parts[0].lower()
        query = parts[1] if len(parts) > 1 else ""

        channel_id = payload.broadcaster.id
        config = await self.command_configs.find_by_name_or_alias(channel_id, cmd_name)

        if not config or not config.enabled or config.command_type != "custom":
            return

        if not config.custom_response and not config.redirect_to:
            return

        # Guard checks (role + cooldown)
        if not has_role(payload.chatter, config.min_role):
            return

        user_id = str(payload.chatter.id)
        if is_on_cooldown(channel_id, config.command_name, user_id, config):
            return

        record_cooldown(channel_id, config.command_name, user_id)

        if config.custom_response:
            response = config.custom_response
            response = response.replace(
                "$(user)", payload.chatter.display_name or payload.chatter.name or ""
            )
            response = response.replace("$(query)", query)
            await payload.broadcaster.send_message(
                message=response,
                sender=self.bot_id,
                token_for=self.bot_id,
            )
            LOGGER.info(f"Custom command: !{cmd_name} -> text response")
        elif config.redirect_to:
            redirect = config.redirect_to.replace("$(query)", query).strip()
            payload.text = f"!{redirect}"
            LOGGER.info(f"Custom command: !{cmd_name} -> !{redirect}")

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def add_token(
        self, token: str, refresh: str
    ) -> twitchio.authentication.ValidateTokenPayload:
        resp: twitchio.authentication.ValidateTokenPayload = await super().add_token(token, refresh)

        if resp.user_id:
            await self.channels.upsert_token_only(resp.user_id, token, refresh)

        login = resp.login or "unknown"
        LOGGER.info(f"Added token to database: {login} ({resp.user_id})")
        return resp

    async def load_tokens(self, path: str | None = None) -> None:
        tokens = await self.channels.list_tokens()

        for tok in tokens:
            try:
                user_info = await self.add_token(tok.token, tok.refresh)
            except twitchio.exceptions.InvalidTokenException as e:
                LOGGER.warning(
                    f"Invalid token for user_id {tok.user_id}, skipping. "
                    f"User needs to re-authenticate: {e}"
                )
                continue

            try:
                await self.add_channel_to_db(tok.user_id, user_info.login or "unknown")
            except Exception as e:
                LOGGER.error(f"Failed to add channel for user_id {tok.user_id}: {e}")

    # ------------------------------------------------------------------
    # Channel management
    # ------------------------------------------------------------------

    async def load_channels(self) -> list[str]:
        enabled = await self.channels.list_enabled_channels()
        names = [ch.channel_name for ch in enabled]
        LOGGER.info(f"Loaded {len(names)} channels from database")
        return names

    async def add_channel_to_db(self, channel_id: str, channel_name: str) -> None:
        if channel_id == self._bot_id:
            LOGGER.debug(f"Skipping bot's own channel: {channel_name}")
            return

        await self.channels.upsert_channel(channel_id, channel_name.lower(), enabled=True)
        LOGGER.info(f"Added channel {channel_name} (ID: {channel_id}) to database")

    async def remove_channel_from_db(self, channel_name: str) -> None:
        await self.channels.disable_channel_by_name(channel_name.lower())
        LOGGER.info(f"Disabled channel {channel_name} in database")

    async def subscribe_channel_events(self, broadcaster_user_id: str) -> None:
        if broadcaster_user_id in self._subscribed_channels:
            LOGGER.debug(f"Already subscribed: {broadcaster_user_id}")
            return

        try:
            subs = get_channel_subscriptions(broadcaster_user_id, self._bot_id)
            resp = await self.multi_subscribe(subs)
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
                self._subscription_ids[broadcaster_user_id] = subscription_ids

            self._subscribed_channels.add(broadcaster_user_id)
            LOGGER.info(f"Subscribed to events for channel: {broadcaster_user_id}")

        except Exception as e:
            LOGGER.exception(f"Failed to subscribe channel {broadcaster_user_id}: {e}")

    async def unsubscribe_channel_events(self, broadcaster_user_id: str) -> None:
        if broadcaster_user_id not in self._subscribed_channels:
            LOGGER.debug(f"Not subscribed to channel: {broadcaster_user_id}")
            return

        try:
            subscription_ids = self._subscription_ids.get(broadcaster_user_id, [])

            if subscription_ids:
                for sub_id in subscription_ids:
                    try:
                        await self.delete_eventsub_subscription(sub_id)
                        LOGGER.debug(
                            f"Deleted subscription {sub_id} for channel {broadcaster_user_id}"
                        )
                    except Exception as e:
                        LOGGER.warning(f"Failed to delete subscription {sub_id}: {e}")

                del self._subscription_ids[broadcaster_user_id]
            else:
                LOGGER.warning(f"No subscription IDs found for channel {broadcaster_user_id}")

            self._subscribed_channels.discard(broadcaster_user_id)
            LOGGER.info(f"Unsubscribed from events for channel: {broadcaster_user_id}")

        except Exception as e:
            LOGGER.exception(f"Failed to unsubscribe channel {broadcaster_user_id}: {e}")

    # ------------------------------------------------------------------
    # PG NOTIFY handlers
    # ------------------------------------------------------------------

    async def _handle_channel_toggle(self, connection, pid, channel, payload) -> None:
        try:
            LOGGER.info(f"[NOTIFY] Received raw notification on channel '{channel}': {payload}")

            data = json.loads(payload)
            channel_id = data["channel_id"]
            enabled = data["enabled"]

            if channel_id == self._bot_id:
                LOGGER.debug(f"[NOTIFY] Ignoring toggle for bot's own channel: {channel_id}")
                return

            LOGGER.info(
                f"[NOTIFY] Processing channel toggle: {channel_id} -> {'ENABLE' if enabled else 'DISABLE'}"
            )

            if enabled:
                if channel_id not in self._subscribed_channels:
                    await self.subscribe_channel_events(channel_id)
                    LOGGER.info(f"[NOTIFY] Instantly subscribed to channel: {channel_id}")
                else:
                    LOGGER.info(f"[NOTIFY] Channel {channel_id} already subscribed, skipping")
            else:
                if channel_id in self._subscribed_channels:
                    await self.unsubscribe_channel_events(channel_id)
                    LOGGER.info(f"[NOTIFY] Instantly unsubscribed from channel: {channel_id}")
                else:
                    LOGGER.info(f"[NOTIFY] Channel {channel_id} not subscribed, skipping")

        except Exception as e:
            LOGGER.exception(f"[NOTIFY] Error handling channel toggle notification: {e}")

    async def _handle_new_token(self, connection, pid, channel, payload) -> None:
        try:
            LOGGER.info(f"[NOTIFY] Received new token notification: {payload}")

            data = json.loads(payload)
            user_id = data["user_id"]

            if user_id == self._bot_id:
                LOGGER.debug(f"[NOTIFY] Ignoring new token for bot's own account: {user_id}")
                return

            token_obj = await self.channels.get_token(user_id)
            if not token_obj:
                LOGGER.warning(f"[NOTIFY] Token not found for user_id: {user_id}")
                return

            try:
                user_info = await self.add_token(token_obj.token, token_obj.refresh)
                LOGGER.info(f"[NOTIFY] Loaded token for new user: {user_info.login} ({user_id})")

                await self.add_channel_to_db(user_id, user_info.login or "unknown")

                if user_id not in self._subscribed_channels:
                    await self.subscribe_channel_events(user_id)
                    LOGGER.info(f"[NOTIFY] Instantly subscribed to new channel: {user_id}")

            except twitchio.exceptions.InvalidTokenException as e:
                LOGGER.warning(f"[NOTIFY] Invalid token for new user {user_id}: {e}")

        except Exception as e:
            LOGGER.exception(f"[NOTIFY] Error handling new token notification: {e}")

    # ------------------------------------------------------------------
    # Startup tasks
    # ------------------------------------------------------------------

    async def _subscribe_initial_channels(self) -> None:
        """Subscribe to EventSub for all enabled channels on startup."""
        try:
            await asyncio.sleep(2)

            enabled_channels = await self.channels.list_enabled_channels()
            LOGGER.info(f"Subscribing to {len(enabled_channels)} enabled channels...")

            for ch in enabled_channels:
                if ch.channel_id == self._bot_id:
                    continue
                await self.subscribe_channel_events(ch.channel_id)
                try:
                    await self.command_configs.ensure_defaults(ch.channel_id)
                    await self.redemption_configs.ensure_defaults(ch.channel_id)
                except Exception as e:
                    LOGGER.warning(f"Failed to ensure defaults for {ch.channel_id}: {e}")

            LOGGER.info("Initial channel subscription complete")
        except Exception as e:
            LOGGER.exception(f"Error subscribing to initial channels: {e}")

    async def _recover_active_sessions(self) -> None:
        """Recover sessions for channels that are currently live on bot startup."""
        try:
            await asyncio.sleep(5)

            enabled_channels = await self.channels.list_enabled_channels()
            if not enabled_channels:
                return

            channel_ids = [
                ch.channel_id for ch in enabled_channels if ch.channel_id != self._bot_id
            ]
            if not channel_ids:
                return

            LOGGER.info(f"Checking for active streams on {len(channel_ids)} channels...")

            streams = await self.fetch_streams(user_ids=channel_ids)  # type: ignore[arg-type]
            if not streams:
                LOGGER.info("No active streams found during startup recovery")
                return

            LOGGER.info(f"Found {len(streams)} active streams, recovering sessions...")

            for stream in streams:
                channel_id = stream.user.id if stream.user else None
                if not channel_id:
                    continue

                if channel_id in self._active_sessions:
                    LOGGER.debug(f"Session already active for channel {channel_id}, skipping")
                    continue

                existing_session = await self.analytics.get_active_session(channel_id)
                if existing_session:
                    self._active_sessions[channel_id] = existing_session["id"]
                    LOGGER.info(
                        f"Resumed existing session {existing_session['id']} for channel {channel_id}"
                    )
                    continue

                title = stream.title
                game_name = stream.game_name
                started_at = stream.started_at or datetime.now()

                session_id = await self.analytics.create_session(
                    channel_id=channel_id,
                    started_at=started_at,
                    title=title,
                    game_name=game_name,
                )
                self._active_sessions[channel_id] = session_id
                LOGGER.info(
                    f"Created recovery session {session_id} for live channel {channel_id} "
                    f"(started: {started_at})"
                )

            LOGGER.info("Session recovery complete")

            await self._sync_vods_for_channels(channel_ids)

        except Exception as e:
            LOGGER.exception(f"Error recovering active sessions: {e}")

    async def _sync_vods_for_channels(
        self, channel_ids: list[str], limit_per_channel: int = 20
    ) -> None:
        """Sync historical VODs from Twitch API for enabled channels."""
        try:
            LOGGER.info(f"Starting VOD sync for {len(channel_ids)} channels...")
            total_synced = 0

            for channel_id in channel_ids:
                try:
                    videos = await self.fetch_videos(  # type: ignore[call-arg]
                        user_id=channel_id,
                        video_type="archive",
                        first=limit_per_channel,
                    )

                    if not videos:
                        continue

                    synced_count = 0
                    for video in videos:
                        started_at = video.created_at
                        if not started_at:
                            continue

                        duration = video.duration
                        ended_at = started_at + duration if duration else started_at  # type: ignore[operator]
                        title = video.title

                        session_id = await self.analytics.sync_session_from_vod(
                            channel_id=channel_id,
                            started_at=started_at,
                            ended_at=ended_at,
                            title=title,
                        )

                        if session_id:
                            synced_count += 1
                            total_synced += 1

                    if synced_count > 0:
                        LOGGER.info(f"Synced {synced_count} VODs for channel {channel_id}")

                except Exception as e:
                    LOGGER.warning(f"Failed to sync VODs for channel {channel_id}: {e}")
                    continue

            if total_synced > 0:
                LOGGER.info(f"VOD sync complete: {total_synced} new sessions imported")
            else:
                LOGGER.info("VOD sync complete: all sessions already up to date")

        except Exception as e:
            LOGGER.exception(f"Error during VOD sync: {e}")
