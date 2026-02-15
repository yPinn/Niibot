"""Twitch Bot class — core lifecycle, event handling, and channel management."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
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

_RANDOM_PATTERN = re.compile(r"\$\(random\s+(\d+)\s*,\s*(\d+)\)")
_PICK_PATTERN = re.compile(r"\$\(pick\s+(.+?)\)")
_COUNT_PATTERN = re.compile(r"\$\(count\)")


def _substitute_variables(
    text: str,
    chatter: twitchio.Chatter,
    channel_name: str,
    query: str,
) -> str:
    """Replace response variables in custom command text.

    Supported variables:
        $(user)             Chatter display name
        $(query)            User input after the command
        $(channel)          Channel name
        $(random min,max)   Random integer in range [min, max]
        $(pick a,b,c)       Random pick from comma-separated items
        $(count)            Command usage count (placeholder)
    """
    text = text.replace("$(user)", chatter.display_name or chatter.name or "")
    text = text.replace("$(query)", query)
    text = text.replace("$(channel)", channel_name or "")

    # $(random min,max) -> random integer in [min, max]
    def _random_replace(m: re.Match) -> str:
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo > hi:
            lo, hi = hi, lo
        return str(random.randint(lo, hi))

    text = _RANDOM_PATTERN.sub(_random_replace, text)

    # $(pick a,b,c) -> random choice from list
    def _pick_replace(m: re.Match) -> str:
        items = [i.strip() for i in m.group(1).split(",") if i.strip()]
        return random.choice(items) if items else ""

    text = _PICK_PATTERN.sub(_pick_replace, text)

    return text


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
        database_url: str,
        subs: list[eventsub.SubscriptionPayload],
    ) -> None:
        self.token_database = token_database
        self._database_url = database_url
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
        asyncio.create_task(pg_listen(self._database_url, "new_token", self._handle_new_token))
        asyncio.create_task(
            pg_listen(self._database_url, "channel_toggle", self._handle_channel_toggle)
        )
        asyncio.create_task(
            pg_listen(self._database_url, "config_change", self._handle_config_change)
        )
        asyncio.create_task(self._recover_active_sessions())
        asyncio.create_task(self._session_verify_loop())
        asyncio.create_task(self._pool_heartbeat_loop())
        asyncio.create_task(self._periodic_cache_refresh())

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

            # Normalize command name to lowercase for case-insensitive matching
            # e.g. "!AI question" → "!ai question", "!Help" → "!help"
            if payload.text and payload.text.startswith("!"):
                parts = payload.text.split(maxsplit=1)
                if parts:
                    parts[0] = parts[0].lower()
                    payload.text = " ".join(parts)

            # Custom command handling: text response or redirect
            handled = await self._handle_custom_command(payload)
            if handled:
                return
        else:
            LOGGER.debug(f"[{payload.chatter.name}]: {payload.text}")

        await super().event_message(payload)

    # ------------------------------------------------------------------
    # Custom command handling
    # ------------------------------------------------------------------

    async def _handle_custom_command(self, payload: twitchio.ChatMessage) -> bool:
        """Handle custom commands: direct text response or redirect to builtin command.

        Returns True if fully handled (text response sent, skip builtin pipeline),
        False if message should continue to builtin command pipeline.
        """
        text = payload.text
        if not text or not text.startswith("!"):
            return False

        parts = text[1:].split(maxsplit=1)
        if not parts or not parts[0]:
            return False

        cmd_name = parts[0].lower()
        query = parts[1] if len(parts) > 1 else ""

        channel_id = payload.broadcaster.id

        # --- Exception Isolation: DB lookups ---
        try:
            config = await self.command_configs.find_by_name_or_alias(channel_id, cmd_name)
        except Exception as e:
            LOGGER.warning(
                f"[GUARD] DB error looking up command '{cmd_name}': {type(e).__name__}: {e}"
            )
            return False

        if not config or not config.enabled or config.command_type != "custom":
            return False

        if not config.custom_response:
            return False

        # Guard checks (role + cooldown)
        if not has_role(payload.chatter, config.min_role):
            return False

        try:
            channel = await self.channels.get_channel(channel_id)
        except Exception as e:
            LOGGER.warning(
                f"[GUARD] DB error fetching channel {channel_id}: {type(e).__name__}: {e}"
            )
            channel = None

        if is_on_cooldown(channel_id, config.command_name, config, channel):
            return False

        record_cooldown(channel_id, config.command_name)

        response = config.custom_response
        if response.startswith("!"):
            # Redirect: rewrite payload and let builtin pipeline handle it
            redirect = response[1:].replace("$(query)", query).strip()
            payload.text = f"!{redirect}"
            LOGGER.info(f"Custom command: !{cmd_name} -> !{redirect}")
            return False
        else:
            # Text response with variable substitution — fully handled
            response = _substitute_variables(
                response, payload.chatter, payload.broadcaster.name or "", query
            )
            await payload.broadcaster.send_message(
                message=response,
                sender=self.bot_id,
                token_for=self.bot_id,
                reply_to_message_id=str(payload.id),
            )
            LOGGER.info(f"Custom command: !{cmd_name} -> text response")
            return True

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
                    try:
                        await self.command_configs.ensure_defaults(channel_id)
                        await self.redemption_configs.ensure_defaults(
                            channel_id, owner_id=self.owner_id
                        )
                        count = await self.command_configs.warm_cache(channel_id)
                        LOGGER.info(f"[NOTIFY] Warmed cache: {count} configs for {channel_id}")
                    except Exception as e:
                        LOGGER.warning(f"[NOTIFY] Failed to warm cache for {channel_id}: {e}")
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

    async def _handle_config_change(self, connection, pid, channel, payload) -> None:
        """Reload in-memory cache for the affected channel on config writes."""
        try:
            data = json.loads(payload)
            channel_id = data.get("channel_id")
            table = data.get("table", "")
            if not channel_id or channel_id not in self._subscribed_channels:
                return

            LOGGER.info(f"[NOTIFY] Config change on {table} for {channel_id}, refreshing cache")
            await self._refresh_channel_cache(channel_id)
        except Exception as e:
            LOGGER.warning(f"[NOTIFY] Error handling config_change: {e}")

    async def _refresh_channel_cache(self, channel_id: str) -> None:
        """Reload all config caches for a single channel from DB."""
        try:
            await self.command_configs.warm_cache(channel_id)
        except Exception as e:
            LOGGER.warning(f"Cache refresh (commands) failed for {channel_id}: {e}")
        try:
            # Invalidate channel record so next read re-fetches
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

    async def _periodic_cache_refresh(self) -> None:
        """Safety net: reload all config caches every 5 minutes.

        Catches any pg_notify misses (e.g. LISTEN connection dropped).
        """
        await asyncio.sleep(300)
        while True:
            try:
                for channel_id in list(self._subscribed_channels):
                    await self._refresh_channel_cache(channel_id)
                LOGGER.debug(
                    f"Periodic cache refresh complete for {len(self._subscribed_channels)} channels"
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                LOGGER.warning(f"Periodic cache refresh error: {e}")
            await asyncio.sleep(300)

    # ------------------------------------------------------------------
    # Startup tasks
    # ------------------------------------------------------------------

    async def _subscribe_initial_channels(self) -> None:
        """Subscribe to EventSub for all enabled channels on startup."""
        try:
            await asyncio.sleep(2)

            enabled_channels = await self.channels.list_enabled_channels()
            LOGGER.info(f"Subscribing to {len(enabled_channels)} enabled channels...")

            # Pre-warm channel cache so get_channel() has stale fallback
            warmed_channels = self.channels.warm_channel_cache(enabled_channels)
            LOGGER.info(f"Warmed channel cache: {warmed_channels} channels")

            total_warmed = 0
            for ch in enabled_channels:
                if ch.channel_id == self._bot_id:
                    continue
                await self.subscribe_channel_events(ch.channel_id)
                try:
                    await self.command_configs.ensure_defaults(ch.channel_id)
                    await self.redemption_configs.ensure_defaults(
                        ch.channel_id, owner_id=self.owner_id
                    )
                    count = await self.command_configs.warm_cache(ch.channel_id)
                    total_warmed += count
                except Exception as e:
                    LOGGER.warning(f"Failed to ensure defaults for {ch.channel_id}: {e}")

            LOGGER.info(
                f"Initial channel subscription complete — warmed cache: {total_warmed} configs"
            )
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
                game_id = str(stream.game_id) if stream.game_id else None
                started_at = stream.started_at or datetime.now()

                session_id = await self.analytics.create_session(
                    channel_id=channel_id,
                    started_at=started_at,
                    title=title,
                    game_name=game_name,
                    game_id=game_id,
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

    async def _session_verify_loop(self) -> None:
        """Poll all enabled channels against Twitch API every 3 min."""
        await asyncio.sleep(120)
        while True:
            try:
                enabled = await self.channels.list_enabled_channels()
                all_ids = [ch.channel_id for ch in enabled if ch.channel_id != self._bot_id]

                if not all_ids:
                    await asyncio.sleep(180)
                    continue

                # Query Twitch for live status
                streams = await self.fetch_streams(user_ids=all_ids)  # type: ignore[arg-type]
                live_map: dict[str, twitchio.Stream] = {}
                if streams:
                    for s in streams:
                        if s.user:
                            live_map[s.user.id] = s

                # Start sessions for live channels without one
                for cid, stream in live_map.items():
                    if cid in self._active_sessions:
                        continue
                    existing = await self.analytics.get_active_session(cid)
                    if existing:
                        self._active_sessions[cid] = existing["id"]
                        continue
                    started_at = stream.started_at or datetime.now()
                    game_id = str(stream.game_id) if stream.game_id else None
                    sid = await self.analytics.create_session(
                        channel_id=cid,
                        started_at=started_at,
                        title=stream.title,
                        game_name=stream.game_name,
                        game_id=game_id,
                    )
                    self._active_sessions[cid] = sid
                    LOGGER.info(f"Session {sid} created for channel {cid} (poll)")

                # End sessions for channels no longer live
                for cid in list(self._active_sessions):
                    if cid in live_map:
                        continue
                    sid = self._active_sessions.pop(cid)
                    self._chatter_buffers.pop(cid, None)
                    if sid:
                        try:
                            await self.analytics.end_session(sid, datetime.now())
                            LOGGER.info(f"Session {sid} ended for channel {cid} (poll)")
                        except Exception as e:
                            LOGGER.warning(f"Failed to end session {sid}: {e}")

                # Safety net: close stale DB sessions >12h
                closed = await self.analytics.close_stale_sessions(max_hours=12)
                if closed:
                    LOGGER.info(f"Closed {closed} stale session(s)")

                # VOD reconciliation
                await self._reconcile_recent_sessions()

            except asyncio.CancelledError:
                break
            except Exception as e:
                LOGGER.warning(f"Session verify error: {e}")
            await asyncio.sleep(180)

    async def _reconcile_recent_sessions(self) -> None:
        """Use Twitch VOD data to fix session durations."""
        try:
            enabled_channels = await self.channels.list_enabled_channels()
            if not enabled_channels:
                return

            for ch in enabled_channels:
                if ch.channel_id == self._bot_id:
                    continue
                try:
                    videos = await self.fetch_videos(  # type: ignore[call-arg]
                        user_id=ch.channel_id,
                        video_type="archive",
                        first=5,
                    )
                    if not videos:
                        continue

                    vods = []
                    for v in videos:
                        if v.created_at and v.duration:
                            vods.append(
                                {
                                    "started_at": v.created_at,
                                    "ended_at": v.created_at + v.duration,  # type: ignore[operator]
                                }
                            )

                    updated = await self.analytics.reconcile_sessions_with_vods(ch.channel_id, vods)
                    if updated:
                        LOGGER.info(f"Reconciled {updated} session(s) for channel {ch.channel_id}")
                except Exception as e:
                    LOGGER.debug(f"VOD reconcile failed for {ch.channel_id}: {e}")
        except Exception as e:
            LOGGER.warning(f"Session reconciliation error: {e}")

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

    async def _pool_heartbeat_loop(self) -> None:
        """Periodically ping the DB pool to keep the idle connection alive.

        Constraint chain: heartbeat(25s) < max_inactive(45s) < Supavisor(~60s).
        With min_size=1 the heartbeat covers the single idle connection.
        """
        while True:
            await asyncio.sleep(25)
            try:
                async with self.token_database.acquire(timeout=10.0) as conn:
                    await conn.fetchval("SELECT 1")
                LOGGER.debug("Pool heartbeat OK")
            except asyncio.CancelledError:
                break
            except Exception as e:
                LOGGER.warning(f"Pool heartbeat failed: {type(e).__name__}: {e}")
