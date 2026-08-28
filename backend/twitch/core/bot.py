"""Twitch Bot class — core lifecycle, event handling, and channel management."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime

import asyncpg
import httpx
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
from shared.log_context import bound_log_context
from shared.repositories.analytics import AnalyticsRepository
from shared.repositories.channel import ChannelRepository
from shared.repositories.command_config import (
    CommandConfigRepository,
    RedemptionConfigRepository,
)
from shared.repositories.message_trigger import MessageTriggerRepository
from shared.repositories.timer import TimerConfigRepository
from utils.mod_guard import mod_guard_notifier

LOGGER: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SharedChatSession:
    """Snapshot of an active Shared Chat session, deduplicated per session_id.

    `participants` is a tuple of (user_id, login) pairs for ALL channels in
    the session (host + guests). `our_channel_ids` records which of our
    monitored channels joined the session, in arrival order — the first
    entry is the canonical logger for update events.
    """

    session_id: str
    host_id: str
    host_name: str
    participants: tuple[tuple[str, str], ...]
    started_at: datetime
    our_channel_ids: tuple[str, ...]


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
        self._channel_names: dict[str, str] = {}  # channel_id → login_name for log enrichment
        self._bot_id = bot_id

        self.channels = ChannelRepository(token_database)
        self.analytics = AnalyticsRepository(token_database)
        self.command_configs = CommandConfigRepository(token_database)
        self.redemption_configs = RedemptionConfigRepository(token_database)
        self.timer_configs = TimerConfigRepository(token_database)
        self.message_trigger_configs = MessageTriggerRepository(token_database)
        self._active_sessions: dict[str, int] = {}
        # Channels currently mid-way through session creation — prevents double-create
        # between event_stream_online and _session_verify_loop running concurrently.
        self._session_creating: set[str] = set()
        # In-memory chatter buffers: {channel_id: {user_id: {"username": str, "count": int, "last_at": datetime}}}
        self._chatter_buffers: dict[str, dict[str, dict]] = {}
        # Per-channel cumulative message count during active sessions (for timer min_lines gate)
        self._channel_line_counts: dict[str, int] = {}
        # Strong references to background tasks to prevent GC collection
        self._background_tasks: set[asyncio.Task] = set()
        # Active Shared Chat sessions keyed by session_id (NOT channel_id), so
        # a session two of our channels co-participate in is tracked once.
        # User-token messages are automatically source-only (Twitch API design),
        # so this map is for awareness/logging rather than routing decisions.
        self._shared_chat_sessions: dict[str, SharedChatSession] = {}
        # Debounced batching for periodic token-refresh logs (single line per burst).
        self._token_refresh_buffer: list[str] = []
        self._token_refresh_flush_task: asyncio.Task | None = None
        # Channels missing one or more BROADCASTER_SCOPES — notified on next stream online
        self._needs_reauth: set[str] = set()
        # Channel IDs where bot has confirmed moderator status
        self._bot_is_mod: set[str] = set()
        # Channel IDs where mod status check is in-flight (suppress guard notifications)
        self._mod_check_pending: set[str] = set()
        # Bot's own login name (set during load_tokens)
        self._bot_login: str = ""

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
                    LOGGER.error("Failed to load component %s: %s", module_name, e)

        for coro in (
            self._subscribe_initial_channels(),
            pg_listen(self._database_url, "new_token", self._handle_new_token),
            pg_listen(self._database_url, "token_reauth", self._handle_token_reauth),
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
        LOGGER.info("Successfully logged in as: %s", self.bot_id)

    async def event_eventsub_notification(self, payload) -> None:
        LOGGER.debug("EventSub notification received: %s", type(payload).__name__)

    async def event_eventsub_ready(self) -> None:
        LOGGER.info("EventSub is ready to receive notifications")

    async def event_eventsub_error(self, error: Exception) -> None:
        LOGGER.error("EventSub error: %s", error)

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
                LOGGER.info("Owner channel authorized and added: %s (ID: %s)", user.name, user.id)
            else:
                LOGGER.info("Channel authorized and added: %s (ID: %s)", user.name, user.id)

        # Admission gate: do not join a channel that is not enabled (owner not
        # approved). enabled is admission-driven (migration 084); approval flips
        # it, which fires channel_toggle → _handle_channel_toggle subscribes then.
        channel = await self.channels.get_channel(payload.user_id)
        if not channel or not channel.enabled:
            LOGGER.info(
                "Channel %s authorized but not enabled (awaiting admission) — not subscribing",
                payload.user_id,
            )
            return

        if payload.user_id not in self._subscribed_channels:
            await self.subscribe_channel_events(payload.user_id)
        else:
            LOGGER.debug("Channel %s already subscribed, skipping", payload.user_id)

        await self._check_bot_mod_status(payload.user_id)

    async def event_token_refreshed(self, payload: _TokenRefreshedPayload) -> None:
        if not payload.user_id:
            return
        scopes_str = " ".join(list(payload.scopes)) if payload.scopes else None
        token_type = "bot" if payload.user_id == self._bot_id else "broadcaster"
        await self.channels.upsert_token_only(
            payload.user_id,
            payload.token,
            payload.refresh_token,
            scopes=scopes_str,
            token_type=token_type,
        )
        LOGGER.debug("[%s] Token refreshed and persisted", self._ch(payload.user_id))
        self._buffer_token_refresh_log(payload.user_id)
        if (
            payload.user_id != self._bot_id
            and payload.user_id not in self._bot_is_mod
            and payload.user_id not in self._needs_reauth
        ):
            LOGGER.debug(
                "[%s] Re-checking mod status after token refresh", self._ch(payload.user_id)
            )
            await self._check_bot_mod_status(payload.user_id)

    def _buffer_token_refresh_log(self, user_id: str) -> None:
        """Collect token-refresh events; flush a single batched INFO line after a quiet window."""
        self._token_refresh_buffer.append(user_id)
        if self._token_refresh_flush_task and not self._token_refresh_flush_task.done():
            self._token_refresh_flush_task.cancel()
        task = asyncio.create_task(self._flush_token_refresh_log())
        self._token_refresh_flush_task = task
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _flush_token_refresh_log(self) -> None:
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            return
        if not self._token_refresh_buffer:
            return
        ids = self._token_refresh_buffer[:]
        self._token_refresh_buffer.clear()
        names = ",".join(self._ch(uid) for uid in ids)
        LOGGER.info("Token refresh: %d channels [%s]", len(ids), names)

    async def event_message(self, payload: twitchio.ChatMessage) -> None:
        if not payload.broadcaster:
            LOGGER.debug("[%s]: %s", payload.chatter.name, payload.text)
            await super().event_message(payload)
            return

        # Bind the channel for every log line emitted while this message is
        # handled (custom commands, triggers, and the twitchio command
        # dispatch in super().event_message all run inside this scope).
        with bound_log_context(
            channel=payload.broadcaster.name,
            channel_id=payload.broadcaster.id,
            chatter=payload.chatter.name,
        ):
            await self._handle_broadcaster_message(payload)

    async def _handle_broadcaster_message(self, payload: twitchio.ChatMessage) -> None:
        LOGGER.debug("[%s#%s]: %s", payload.chatter.name, payload.broadcaster.name, payload.text)

        if payload.broadcaster.id not in self._subscribed_channels:
            LOGGER.debug("Ignoring message from unsubscribed channel: %s", payload.broadcaster.name)
            return

        # Skip messages that originated in a shared-chat partner's channel —
        # source_broadcaster is set only when the message came from a different
        # channel in an active shared-chat session.  The partner's own
        # subscription fires a separate event where source_broadcaster is None,
        # so processing there avoids duplicate command responses across channels.
        if payload.source_broadcaster is not None:
            LOGGER.debug(
                "Skipping shared-chat message from %s seen in %s",
                payload.source_broadcaster.name,
                payload.broadcaster.name,
            )
            return

        channel_id = payload.broadcaster.id
        chatter_id = payload.chatter.id

        # Ignore bot's own messages — prevents self-triggering loops
        if chatter_id == self.bot_id:
            return

        if channel_id in self._needs_reauth:
            from utils.reauth import CMD_COOLDOWN, reauth_notifier

            is_command = bool(payload.text and payload.text.startswith("!"))
            await reauth_notifier.notify(
                broadcaster_login=payload.broadcaster.name,
                channel_id=channel_id,
                send_fn=lambda msg: payload.broadcaster.send_message(
                    message=msg,
                    sender=self.bot_id,
                ),
                min_interval=CMD_COOLDOWN if is_command else None,
            )
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
            self._channel_line_counts[channel_id] = self._channel_line_counts.get(channel_id, 0) + 1

        # Mod guard: block all functionality until bot has mod in this channel.
        # Skip notification while the status check is still in-flight.
        if channel_id not in self._bot_is_mod:
            if channel_id in self._mod_check_pending:
                LOGGER.debug("[%s] Mod check in-flight, deferring guard", payload.broadcaster.name)
                return
            await mod_guard_notifier.notify(
                broadcaster_login=payload.broadcaster.name or "",
                channel_id=channel_id,
                bot_login=self._bot_login,
                send_fn=lambda msg: payload.broadcaster.send_message(
                    message=msg,
                    sender=self.bot_id,
                ),
            )
            return

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

        await super().event_message(payload)

    @staticmethod
    def _shared_chat_participants(
        payload: twitchio.SharedChatSessionBegin | twitchio.SharedChatSessionUpdate,
    ) -> tuple[tuple[str, str], ...]:
        # PartialUser.name is Optional (e.g. deleted accounts); fall back to id for logging.
        return tuple((str(p.id), p.name or str(p.id)) for p in payload.participants)

    @staticmethod
    def _format_parties(
        participants: tuple[tuple[str, str], ...],
        self_ids: frozenset[str],
        host_id: str,
    ) -> str:
        """Render party list with inline role tags: name(host), name(self), name(self,host)."""

        def tag(pid: str) -> str:
            tags = []
            if pid in self_ids:
                tags.append("self")
            if pid == host_id:
                tags.append("host")
            return f"({','.join(tags)})" if tags else ""

        return ",".join(f"{name}{tag(pid)}" for pid, name in participants)

    async def event_shared_chat_begin(self, payload: twitchio.SharedChatSessionBegin) -> None:
        channel_id = str(payload.broadcaster.id)
        session_id = payload.session_id
        participants = self._shared_chat_participants(payload)
        existing = self._shared_chat_sessions.get(session_id)

        if existing is None:
            session = SharedChatSession(
                session_id=session_id,
                host_id=str(payload.host.id),
                host_name=payload.host.name or str(payload.host.id),
                participants=participants,
                started_at=datetime.now(UTC),
                our_channel_ids=(channel_id,),
            )
            self._shared_chat_sessions[session_id] = session
            LOGGER.info(
                "SharedChat begin session=%s parties=%s",
                session_id,
                self._format_parties(
                    participants, frozenset(session.our_channel_ids), session.host_id
                ),
            )
            return

        # Another of our channels joined the same session — silent merge.
        if channel_id not in existing.our_channel_ids:
            self._shared_chat_sessions[session_id] = replace(
                existing,
                participants=participants,
                our_channel_ids=existing.our_channel_ids + (channel_id,),
            )

    async def event_shared_chat_update(self, payload: twitchio.SharedChatSessionUpdate) -> None:
        channel_id = str(payload.broadcaster.id)
        session_id = payload.session_id
        new_participants = self._shared_chat_participants(payload)
        prev = self._shared_chat_sessions.get(session_id)

        if prev is None:
            # Update arrived before begin (rare) — synthesize and log as begin.
            session = SharedChatSession(
                session_id=session_id,
                host_id=str(payload.host.id),
                host_name=payload.host.name or str(payload.host.id),
                participants=new_participants,
                started_at=datetime.now(UTC),
                our_channel_ids=(channel_id,),
            )
            self._shared_chat_sessions[session_id] = session
            LOGGER.info(
                "SharedChat begin session=%s parties=%s",
                session_id,
                self._format_parties(
                    new_participants, frozenset(session.our_channel_ids), session.host_id
                ),
            )
            return

        prev_ids = {pid for pid, _ in prev.participants}
        new_ids = {pid for pid, _ in new_participants}
        joined = [name for pid, name in new_participants if pid not in prev_ids]
        left = [name for pid, name in prev.participants if pid not in new_ids]

        our_ids = prev.our_channel_ids
        if channel_id not in our_ids:
            our_ids = our_ids + (channel_id,)
        self._shared_chat_sessions[session_id] = replace(
            prev, participants=new_participants, our_channel_ids=our_ids
        )

        # Only the canonical (first) of our channels in this session logs updates.
        if channel_id != our_ids[0]:
            return
        if not joined and not left:
            return
        LOGGER.info(
            "SharedChat update session=%s +%s -%s",
            session_id,
            ",".join(joined) or "—",
            ",".join(left) or "—",
        )

    async def event_shared_chat_end(self, payload: twitchio.SharedChatSessionEnd) -> None:
        channel_id = str(payload.broadcaster.id)
        session_id = payload.session_id
        prev = self._shared_chat_sessions.get(session_id)

        if prev is None:
            # End arrived without a tracked begin (e.g. bot restarted mid-session).
            LOGGER.info("SharedChat end session=%s", session_id)
            return

        remaining = tuple(c for c in prev.our_channel_ids if c != channel_id)
        if remaining:
            # Other of our channels still in this session — silent.
            self._shared_chat_sessions[session_id] = replace(prev, our_channel_ids=remaining)
            return

        # Last of our channels leaving — log end and drop the session.
        duration = int((datetime.now(UTC) - prev.started_at).total_seconds())
        LOGGER.info(
            "SharedChat end session=%s duration=%ds parties=%s",
            session_id,
            duration,
            self._format_parties(prev.participants, frozenset(prev.our_channel_ids), prev.host_id),
        )
        del self._shared_chat_sessions[session_id]

    async def event_command_error(self, payload: commands.CommandErrorPayload) -> None:
        """Suppress CommandNotFound to avoid log noise from unknown commands."""
        if isinstance(payload.exception, CommandNotFound):
            return
        ctx = getattr(payload, "context", None)
        command = getattr(getattr(ctx, "command", None), "name", None)
        channel = getattr(getattr(ctx, "broadcaster", None), "name", None)
        with bound_log_context(command=command, channel=channel):
            LOGGER.error("Command error: %s", payload.exception)

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def add_token(
        self, token: str, refresh: str
    ) -> twitchio.authentication.ValidateTokenPayload:
        resp: twitchio.authentication.ValidateTokenPayload = await super().add_token(token, refresh)

        if resp.user_id:
            token_type = "bot" if resp.user_id == self._bot_id else "broadcaster"
            for attempt in range(1, 4):
                try:
                    await self.channels.upsert_token_only(
                        resp.user_id, token, refresh, token_type=token_type
                    )
                    break
                except Exception as e:
                    if attempt < 3:
                        LOGGER.warning("save_token attempt %s/3 failed: %s", attempt, e)
                        await asyncio.sleep(2)
                    else:
                        LOGGER.error("save_token failed after 3 attempts: %s", e)

        login = resp.login or "unknown"
        LOGGER.info("[%s] Token added to database (%s)", login, resp.user_id)
        return resp

    async def load_tokens(self, path: str | None = None) -> None:
        tokens = await self.channels.list_tokens()

        for tok in tokens:
            # Load the correct token type per account:
            # bot account → only 'bot' token; all others → only 'broadcaster' token.
            expected_type = "bot" if tok.user_id == self._bot_id else "broadcaster"
            if tok.token_type != expected_type:
                continue

            try:
                user_info = await self.add_token(tok.token, tok.refresh)
            except twitchio.exceptions.InvalidTokenException as e:
                LOGGER.warning(
                    "Invalid token for user_id %s, skipping. User needs to re-authenticate: %s",
                    tok.user_id,
                    e,
                )
                continue

            if tok.user_id == self._bot_id:
                self._bot_login = user_info.login or ""
                if "user:bot" not in user_info.scopes:
                    LOGGER.warning(
                        "Bot token is missing 'user:bot' scope — bot badge will NOT appear "
                        "in chat. Re-authorize: npm run nb -- twitch oauth --role bot"
                    )
                else:
                    LOGGER.info("Bot token has 'user:bot' scope — bot badge enabled.")
                continue  # bot account does not need a channels row

            from utils.reauth import missing_broadcaster_scopes

            missing = missing_broadcaster_scopes(user_info.scopes)
            if missing:
                LOGGER.warning(
                    "Channel %s missing scopes %s — will notify on next stream online.",
                    user_info.login or tok.user_id,
                    missing,
                )
                self._needs_reauth.add(tok.user_id)

            try:
                await self.add_channel_to_db(tok.user_id, user_info.login or "unknown")
            except Exception as e:
                LOGGER.error("Failed to add channel for user_id %s: %s", tok.user_id, e)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    async def _check_bot_mod_status(self, channel_id: str) -> None:
        """Check via Helix API if the bot is a moderator in the channel.

        Populates _bot_is_mod on success. Logs a warning if the check fails
        (missing scope, token error, etc.) and leaves the channel out of _bot_is_mod.
        Callers must not send mod-guard notifications while this is in-flight;
        _mod_check_pending gates that suppression.
        """
        self._mod_check_pending.add(channel_id)
        LOGGER.debug("[%s] Checking mod status", self._ch(channel_id))
        try:
            token_obj = await self.channels.get_token(channel_id)
            if not token_obj:
                LOGGER.debug("[%s] No token, cannot verify mod status", self._ch(channel_id))
                return

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.twitch.tv/helix/moderation/moderators",
                    headers={
                        "Client-Id": self._client_id,
                        "Authorization": f"Bearer {token_obj.token}",
                    },
                    params={"broadcaster_id": channel_id, "user_id": self._bot_id},
                )

            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    was_mod = channel_id in self._bot_is_mod
                    self._bot_is_mod.add(channel_id)
                    LOGGER.info("[%s] Bot confirmed mod", self._ch(channel_id))
                    if not was_mod:
                        # channel.follow needs the bot as moderator — (re)subscribe
                        # now that mod is confirmed (initial attempt 403s pre-mod).
                        await self.resubscribe_follow(channel_id)
                else:
                    LOGGER.info(
                        "[%s] Bot is NOT mod — chat features blocked until /mod is granted",
                        self._ch(channel_id),
                    )
            elif resp.status_code in (401, 403):
                # Token expired or missing scope — broadcaster needs to re-auth, not grant /mod.
                self._needs_reauth.add(channel_id)
                LOGGER.warning(
                    "[%s] Marking for reauth (mod check %s)",
                    self._ch(channel_id),
                    resp.status_code,
                )
            else:
                LOGGER.warning(
                    "[%s] Mod status check failed: %s %s",
                    self._ch(channel_id),
                    resp.status_code,
                    resp.text[:80],
                )
        except Exception as e:
            LOGGER.warning(
                "[%s] Mod status check error: %s: %s", self._ch(channel_id), type(e).__name__, e
            )
        finally:
            self._mod_check_pending.discard(channel_id)

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
                    LOGGER.info("Pool heartbeat recovered after %s failures", fail_count)
                fail_count = 0
                interval = 60
            except asyncio.CancelledError:
                break
            except Exception as e:
                fail_count += 1
                if fail_count <= 3:
                    LOGGER.warning(
                        "Pool heartbeat failed (%s): %s: %s", fail_count, type(e).__name__, e
                    )

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
                        LOGGER.error("Pool reconnect failed: %s: %s", type(re_err).__name__, re_err)
                        fail_count = 0
                        interval = 120
                        continue

                interval = min(60 * (2 ** min(fail_count - 1, 1)), 120)
