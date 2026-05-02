"""Twitch Bot class — core lifecycle, event handling, and channel management."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import asyncpg
import twitchio
from twitchio import eventsub
from twitchio.ext import commands
from twitchio.ext.commands import CommandNotFound
from twitchio.payloads import TokenRefreshedPayload as _TokenRefreshedPayload

from core._channel_mixin import _ChannelMixin
from core._notify_mixin import _NotifyMixin
from core._router_mixin import _MessageRouterMixin
from core._session_mixin import _SessionMixin
from core.config import COMPONENTS_DIR
from core.pg_listener import pg_listen
from shared.database import DatabaseManager
from shared.repositories.analytics import AnalyticsRepository
from shared.repositories.channel import ChannelRepository
from shared.repositories.command_config import (
    CommandConfigRepository,
    RedemptionConfigRepository,
)
from shared.repositories.message_trigger import MessageTriggerRepository
from shared.repositories.timer import TimerConfigRepository

LOGGER: logging.Logger = logging.getLogger(__name__)


class Bot(_ChannelMixin, _MessageRouterMixin, _NotifyMixin, _SessionMixin, commands.AutoBot):
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
        db_manager: DatabaseManager,
        database_url: str,
        subs: list[eventsub.SubscriptionPayload],
    ) -> None:
        self.token_database = token_database
        self._client_id = client_id
        self._db_manager = db_manager
        self._database_url = database_url
        self._subscribed_channels: set[str] = set()
        self._subscription_ids: dict[str, list[str]] = {}
        self._bot_id = bot_id

        self.channels = ChannelRepository(token_database)
        self.analytics = AnalyticsRepository(token_database)
        self.command_configs = CommandConfigRepository(token_database)
        self.redemption_configs = RedemptionConfigRepository(token_database)
        self.timer_configs = TimerConfigRepository(token_database)
        self.message_trigger_configs = MessageTriggerRepository(token_database)
        self._active_sessions: dict[str, int] = {}
        # In-memory chatter buffers: {channel_id: {user_id: {"username": str, "count": int, "last_at": datetime}}}
        self._chatter_buffers: dict[str, dict[str, dict]] = {}
        # Per-channel cumulative message count during active sessions (for timer min_lines gate)
        self._channel_line_counts: dict[str, int] = {}
        # Strong references to background tasks to prevent GC collection
        self._background_tasks: set[asyncio.Task] = set()
        # Channel IDs currently in an active Shared Chat session.
        # User-token messages are automatically source-only (Twitch API design),
        # so this set is for awareness/logging rather than routing decisions.
        self._shared_chat_channels: set[str] = set()

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
                    LOGGER.error(f"Failed to load component {module_name}: {e}")

        for coro in (
            self._subscribe_initial_channels(),
            pg_listen(self._database_url, "new_token", self._handle_new_token),
            pg_listen(self._database_url, "channel_toggle", self._handle_channel_toggle),
            pg_listen(self._database_url, "config_change", self._handle_config_change),
            self._recover_active_sessions(),
            self._session_verify_loop(),
            self._watch_time_loop(),
            self._pool_heartbeat_loop(),
            self._periodic_cache_refresh(),
        ):
            task = asyncio.create_task(coro)
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def event_ready(self) -> None:
        LOGGER.info(f"Successfully logged in as: {self.bot_id}")

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

    async def event_token_refreshed(self, payload: _TokenRefreshedPayload) -> None:
        if not payload.user_id:
            return
        scopes_str = " ".join(list(payload.scopes)) if payload.scopes else None
        await self.channels.upsert_token_only(
            payload.user_id, payload.token, payload.refresh_token, scopes=scopes_str
        )
        LOGGER.info(f"Token refreshed and persisted for user: {payload.user_id}")

    async def event_message(self, payload: twitchio.ChatMessage) -> None:
        if payload.broadcaster:
            LOGGER.debug(f"[{payload.chatter.name}#{payload.broadcaster.name}]: {payload.text}")

            if payload.broadcaster.id not in self._subscribed_channels:
                LOGGER.debug(
                    f"Ignoring message from unsubscribed channel: {payload.broadcaster.name}"
                )
                return

            # Skip messages that originated in a shared-chat partner's channel —
            # source_broadcaster is set only when the message came from a different
            # channel in an active shared-chat session.  The partner's own
            # subscription fires a separate event where source_broadcaster is None,
            # so processing there avoids duplicate command responses across channels.
            if payload.source_broadcaster is not None:
                LOGGER.debug(
                    f"Skipping shared-chat message from {payload.source_broadcaster.name}"
                    f" seen in {payload.broadcaster.name}"
                )
                return

            channel_id = payload.broadcaster.id
            chatter_id = payload.chatter.id

            # Ignore bot's own messages — prevents self-triggering loops
            if chatter_id == self.bot_id:
                return

            if channel_id in self._active_sessions:
                buf = self._chatter_buffers.setdefault(channel_id, {})
                if chatter_id in buf:
                    buf[chatter_id]["count"] += 1
                    buf[chatter_id]["last_at"] = datetime.now(UTC)
                    buf[chatter_id]["username"] = payload.chatter.name
                    buf[chatter_id]["display_name"] = payload.chatter.display_name
                else:
                    buf[chatter_id] = {
                        "username": payload.chatter.name,
                        "display_name": payload.chatter.display_name,
                        "count": 1,
                        "last_at": datetime.now(UTC),
                    }
                self._channel_line_counts[channel_id] = (
                    self._channel_line_counts.get(channel_id, 0) + 1
                )

            if payload.text and payload.text.startswith("!"):
                parts = payload.text.split(maxsplit=1)
                if parts:
                    parts[0] = parts[0].lower()
                    payload.text = " ".join(parts)

            handled = await self._handle_custom_command(payload)
            if handled:
                return

            if payload.text and not payload.text.startswith("!"):
                triggered = await self._handle_message_trigger(payload)
                if triggered:
                    return
        else:
            LOGGER.debug(f"[{payload.chatter.name}]: {payload.text}")

        await super().event_message(payload)

    async def event_shared_chat_begin(self, payload: twitchio.SharedChatSessionBegin) -> None:
        channel_id = str(payload.broadcaster.id)
        self._shared_chat_channels.add(channel_id)
        LOGGER.info(
            f"[{payload.broadcaster.name}] Shared Chat session started "
            f"(session={payload.session_id}, host={payload.host.name}). "
            f"Bot replies use user token → source-only by default."
        )

    async def event_shared_chat_end(self, payload: twitchio.SharedChatSessionEnd) -> None:
        channel_id = str(payload.broadcaster.id)
        self._shared_chat_channels.discard(channel_id)
        LOGGER.info(
            f"[{payload.broadcaster.name}] Shared Chat session ended (session={payload.session_id})."
        )

    async def event_command_error(self, payload: commands.CommandErrorPayload) -> None:
        """Suppress CommandNotFound to avoid log noise from unknown commands."""
        if isinstance(payload.exception, CommandNotFound):
            return
        LOGGER.error(f"Command error: {payload.exception}")

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def add_token(
        self, token: str, refresh: str
    ) -> twitchio.authentication.ValidateTokenPayload:
        resp: twitchio.authentication.ValidateTokenPayload = await super().add_token(token, refresh)

        if resp.user_id:
            for attempt in range(1, 4):
                try:
                    await self.channels.upsert_token_only(resp.user_id, token, refresh)
                    break
                except Exception as e:
                    if attempt < 3:
                        LOGGER.warning(f"save_token attempt {attempt}/3 failed: {e}")
                        await asyncio.sleep(2)
                    else:
                        LOGGER.error(f"save_token failed after 3 attempts: {e}")

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

            if tok.user_id == self._bot_id:
                if "user:bot" not in user_info.scopes:
                    LOGGER.warning(
                        "Bot token is missing 'user:bot' scope — bot badge will NOT appear "
                        "in chat. Re-authorize: python scripts/tw_oauth.py bot"
                    )
                else:
                    LOGGER.info("Bot token has 'user:bot' scope — bot badge enabled.")
                continue  # bot account does not need a channels row

            try:
                await self.add_channel_to_db(tok.user_id, user_info.login or "unknown")
            except Exception as e:
                LOGGER.error(f"Failed to add channel for user_id {tok.user_id}: {e}")

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _refresh_pool_refs(self) -> None:
        """Update all pool references after a reconnect."""
        pool = self._db_manager.pool
        self.token_database = pool
        self.channels.pool = pool
        self.analytics.pool = pool
        self.command_configs.pool = pool
        self.redemption_configs.pool = pool
        self.timer_configs.pool = pool
        self.message_trigger_configs.pool = pool
        for comp in self._components.values():
            if hasattr(comp, "refresh_pool"):
                comp.refresh_pool(pool)

    async def _pool_heartbeat_loop(self) -> None:
        """Periodically ping the DB pool to detect and recover dead connections.

        After 3 consecutive failures, destroys the dead pool and creates a
        fresh one via ``DatabaseManager.reconnect()``.
        """
        interval = 60
        fail_count = 0
        while True:
            await asyncio.sleep(interval)
            try:
                async with self.token_database.acquire(timeout=10.0) as conn:
                    await conn.fetchval("SELECT 1")
                if fail_count > 0:
                    LOGGER.info(f"Pool heartbeat recovered after {fail_count} failures")
                fail_count = 0
                interval = 60
            except asyncio.CancelledError:
                break
            except Exception as e:
                fail_count += 1
                if fail_count <= 3:
                    LOGGER.warning(f"Pool heartbeat failed ({fail_count}): {type(e).__name__}: {e}")

                if fail_count == 3:
                    LOGGER.warning("Pool appears dead, attempting reconnect...")
                    try:
                        await self._db_manager.reconnect()
                        self._refresh_pool_refs()
                        LOGGER.info("Pool reconnected successfully")
                        fail_count = 0
                        interval = 60
                        continue
                    except Exception as re_err:
                        LOGGER.error(f"Pool reconnect failed: {type(re_err).__name__}: {re_err}")
                        fail_count = 0
                        interval = 120
                        continue

                interval = min(60 * (2 ** min(fail_count - 1, 1)), 120)
