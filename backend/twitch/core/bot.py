"""Twitch Bot class — core lifecycle, event handling, and channel management."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

import asyncpg
import httpx
import twitchio
from twitchio import eventsub
from twitchio.ext import commands
from twitchio.ext.commands import CommandNotFound
from twitchio.payloads import TokenRefreshedPayload as _TokenRefreshedPayload

from core._message_router_mixin import _MessageRouterMixin
from core._notify_mixin import _NotifyMixin
from core.config import COMPONENTS_DIR
from core.session_service import SessionService
from core.subscription_manager import SubscriptionManager
from shared.database import DatabaseManager
from shared.log_context import bound_log_context
from shared.pg_listener import pg_listen
from shared.repositories.analytics import AnalyticsRepository
from shared.repositories.channel import ChannelRepository
from shared.repositories.command_config import (
    CommandConfigRepository,
    RedemptionConfigRepository,
)
from shared.repositories.event_config import EventConfigRepository
from shared.repositories.message_trigger import MessageTriggerRepository
from shared.repositories.timer import TimerConfigRepository
from shared.repositories.video_queue import VideoQueueRepository
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


class Bot(_MessageRouterMixin, _NotifyMixin, commands.AutoBot):
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
        self._bot_id = bot_id

        self.channels = ChannelRepository(token_database)
        self.analytics = AnalyticsRepository(token_database)
        self.command_configs = CommandConfigRepository(token_database)
        self.redemption_configs = RedemptionConfigRepository(token_database)
        self.event_configs = EventConfigRepository(token_database)
        self.timer_configs = TimerConfigRepository(token_database)
        self.video_queue = VideoQueueRepository(token_database)
        self.message_trigger_configs = MessageTriggerRepository(token_database)
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
        # Consecutive EventSub websocket closes without an intervening welcome,
        # keyed by the socket's token_for (best-effort — see event_websocket_closed).
        # Used to escalate a stuck reconnect loop from WARNING to ERROR so it
        # actually reaches the Discord webhook instead of only ever hitting
        # TwitchIO's own INFO/DEBUG-level reconnect logging.
        self._eventsub_fail_count: dict[str, int] = {}

        init_kwargs: dict = dict(
            client_id=client_id,
            client_secret=client_secret,
            bot_id=bot_id,
            owner_id=owner_id,
            prefix="!",
            subscriptions=subs,
            force_subscribe=True,
            case_insensitive=True,
        )
        if conduit_id:
            init_kwargs["conduit_id"] = conduit_id

        super().__init__(**init_kwargs)

        # EventSub subscription ownership (was loose _subscribed_channels /
        # _subscription_ids / _channel_names on this class).
        self.subs = SubscriptionManager(
            bot_id=bot_id,
            multi_subscribe=self.multi_subscribe,
            delete_subscription=self.delete_eventsub_subscription,
            needs_reauth=self._needs_reauth,
        )
        # Stream-session ownership (was loose _active_sessions / _session_creating /
        # _chatter_buffers / _channel_line_counts, mutated from 3 places).
        self.sessions = SessionService(
            analytics=self.analytics,
            channels=self.channels,
            subs=self.subs,
            client=self,
            bot_id=bot_id,
            client_id=client_id,
        )

    # ------------------------------------------------------------------
    # Channel helpers
    # ------------------------------------------------------------------

    def _ch(self, channel_id: str) -> str:
        """Return 'login(id)' when the name is known, otherwise just 'id'."""
        return self.subs.ch(channel_id)

    async def add_channel_to_db(self, channel_id: str, channel_name: str) -> None:
        if channel_id == self._bot_id:
            LOGGER.debug(f"Skipping bot's own channel: {channel_name}")
            return

        await self.channels.upsert_channel(channel_id, channel_name.lower(), enabled=True)
        self.subs.remember(channel_id, channel_name)
        LOGGER.info(f"Added channel {channel_name} (ID: {channel_id}) to database")

    async def _bootstrap_channels(self) -> None:
        """Subscribe to EventSub for all enabled channels on startup, then seed
        per-channel config defaults and warm the caches.
        """
        try:
            await asyncio.sleep(2)

            enabled_channels = await self.channels.list_enabled_channels()
            LOGGER.info(f"Subscribing to {len(enabled_channels)} enabled channels...")
            self.subs.remember_many(enabled_channels)

            warmed_channels = self.channels.warm_channel_cache(enabled_channels)
            LOGGER.info(f"Warmed channel cache: {warmed_channels} channels")

            non_bot = [ch for ch in enabled_channels if ch.channel_id != self._bot_id]

            # Pre-add to _mod_check_pending before subscribing: asyncio.gather tasks
            # haven't run their first line yet when the event loop yields, so a
            # message arriving in that window would fire a spurious mod-guard
            # notification.
            subscribed_ids: list[str] = []
            for ch in non_bot:
                self._mod_check_pending.add(ch.channel_id)
                try:
                    await self.subs.subscribe(ch.channel_id)
                    subscribed_ids.append(ch.channel_id)
                except Exception as e:
                    LOGGER.error(
                        f"Failed to subscribe channel {ch.channel_name or ch.channel_id}: {e}"
                    )
                    self._mod_check_pending.discard(ch.channel_id)

            await asyncio.gather(
                *(self._check_bot_mod_status(cid) for cid in subscribed_ids),
                return_exceptions=True,
            )

            total_warmed = 0
            for ch in non_bot:
                total_warmed += await self._seed_and_warm_channel(ch.channel_id)

            LOGGER.info(
                f"Initial channel subscription complete — warmed cache: {total_warmed} configs"
            )
        except Exception as e:
            LOGGER.exception(f"Error subscribing to initial channels: {e}")

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
            self._bootstrap_channels(),
            pg_listen(self._database_url, "new_token", self._handle_new_token),
            pg_listen(self._database_url, "token_reauth", self._handle_token_reauth),
            pg_listen(
                self._database_url,
                "bot_token_updated",
                self._handle_bot_token_updated,
            ),
            pg_listen(self._database_url, "channel_toggle", self._handle_channel_toggle),
            pg_listen(self._database_url, "config_change", self._handle_config_change),
            pg_listen(
                self._database_url,
                "video_queue_now_playing",
                self._handle_video_queue_now_playing,
            ),
            self._pool_heartbeat_loop(),
            self._periodic_cache_refresh(),
        ):
            task = asyncio.create_task(coro)
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

        # Session recovery + verify + watch-time loops (owned by SessionService).
        self.sessions.start()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def event_ready(self) -> None:
        LOGGER.info("Successfully logged in as: %s", self.bot_id)

    async def event_stream_online(self, payload: twitchio.StreamOnline) -> None:
        channel_id = payload.broadcaster.id
        LOGGER.info("[%s] Stream online", payload.broadcaster.name)

        # Proactively surface a reauth problem on go-live — don't wait for a chat message.
        if channel_id in self._needs_reauth:
            from utils.reauth import reauth_notifier

            await reauth_notifier.notify(
                broadcaster_login=payload.broadcaster.name,
                channel_id=channel_id,
                send_fn=lambda msg: payload.broadcaster.send_message(
                    message=msg, sender=self.bot_id
                ),
            )

        await self.sessions.on_stream_online(channel_id)

    async def event_stream_offline(self, payload: twitchio.StreamOffline) -> None:
        LOGGER.info("[%s] Stream offline", payload.broadcaster.name)
        await self.sessions.on_stream_offline(payload.broadcaster.id)

    async def event_subscription_revoked(self, payload: twitchio.SubscriptionRevoked) -> None:
        """Twitch revoked a subscription — the channel silently stops receiving
        this event type. Log it (ERROR+ reaches the error webhook) and flag the
        broadcaster for dashboard reauth if they pulled their token.
        """
        condition = payload.raw.get("condition") or {}
        channel_id = (
            condition.get("broadcaster_user_id")
            or condition.get("to_broadcaster_user_id")
            or condition.get("user_id")
        )
        reason = getattr(payload.status, "value", str(payload.status))
        ch = self._ch(channel_id) if channel_id else "?"

        log = (
            LOGGER.warning if reason in ("authorization_revoked", "user_removed") else LOGGER.error
        )
        log("EventSub subscription revoked: %s type=%s reason=%s", ch, payload.type, reason)

        if reason == "authorization_revoked" and channel_id and channel_id != self._bot_id:
            self.subs.mark_revoked(channel_id)
            await self._mark_reauth_required(channel_id)

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

        if not self.subs.is_subscribed(payload.user_id):
            await self.subs.subscribe(payload.user_id)
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

        if not self.subs.is_subscribed(payload.broadcaster.id):
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

        self.sessions.record_line(
            channel_id, chatter_id, payload.chatter.name or "", payload.chatter.display_name
        )

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

    async def event_error(self, payload: twitchio.EventErrorPayload) -> None:
        """Override the default (unlabeled, no-context) listener-error log so
        non-command EventSub handler crashes carry the same code/channel
        context as command errors, and so they're classified for log search.
        TwitchIO already isolates each listener in its own task — one bad
        handler can't crash the bot or drop the connection either way.
        """
        channel = getattr(getattr(payload.original, "broadcaster", None), "name", None)
        listener_name = getattr(payload.listener, "__name__", repr(payload.listener))
        with bound_log_context(channel=channel):
            LOGGER.error(
                "Unhandled error in event listener '%s': %s",
                listener_name,
                payload.error,
                exc_info=payload.error,
                extra={"code": "RUNTIME.EVENTSUB_HANDLER_FAILED", "event_class": "occasional"},
            )

    # EventSub websocket lifecycle — TwitchIO logs reconnects at INFO/DEBUG,
    # which never reaches ERROR and so never triggers the Discord error
    # webhook. Track consecutive closes-without-a-welcome per socket and
    # escalate once a reconnect loop looks stuck, rather than alerting on
    # every routine Twitch-initiated `session_reconnect`.
    _EVENTSUB_FAIL_THRESHOLD = 3

    async def event_websocket_closed(self, payload: Any) -> None:
        token_for = getattr(getattr(payload, "socket", None), "_token_for", None) or "unknown"
        count = self._eventsub_fail_count.get(token_for, 0) + 1
        self._eventsub_fail_count[token_for] = count
        if count < self._EVENTSUB_FAIL_THRESHOLD:
            LOGGER.warning(
                "EventSub websocket closed for %s (attempt %d)",
                token_for,
                count,
                extra={"code": "RUNTIME.EVENTSUB_DISCONNECTED", "event_class": "persistent"},
            )
        else:
            LOGGER.error(
                "EventSub websocket for %s has not recovered after %d consecutive closes",
                token_for,
                count,
                extra={"code": "RUNTIME.EVENTSUB_RECONNECT_FAILED", "event_class": "persistent"},
            )

    async def event_websocket_welcome(self, payload: Any) -> None:
        # Find which token_for this welcome belongs to via the client's own
        # websocket registry rather than the payload (WebsocketWelcome carries
        # only the session, not the owning socket).
        token_for = next(
            (tf for tf, sockets in self._websockets.items() if payload.id in sockets),  # type: ignore[attr-defined]
            None,
        )
        if token_for is None:
            return
        prior_failures = self._eventsub_fail_count.pop(token_for, 0)
        if prior_failures >= self._EVENTSUB_FAIL_THRESHOLD:
            LOGGER.info(
                "EventSub websocket for %s recovered after %d failures",
                token_for,
                prior_failures,
            )

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

            from shared.twitch_scopes import missing_broadcaster_scopes

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
                        await self.subs.resubscribe_follow(channel_id)
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

    def memory_gauges(self) -> dict[str, int]:
        """Size of every bounded/unbounded in-process dict this bot holds,
        for `/status` and the periodic gauge log — see shared/gauges.py for
        the DB pool + cache-side counterparts. Components that hold their own
        per-channel state report via an optional `memory_gauges()` hook,
        same convention as `refresh_pool()`.
        """
        gauges: dict[str, int] = {
            "needs_reauth": len(self._needs_reauth),
            "bot_is_mod": len(self._bot_is_mod),
            "mod_check_pending": len(self._mod_check_pending),
            "shared_chat_sessions": len(self._shared_chat_sessions),
            "subscribed_channels": len(self.subs.subscribed),
            "subscription_names": self.subs.names_count,
            "eventsub_fail_count_entries": len(self._eventsub_fail_count),
            **self.sessions.memory_gauges(),
        }
        for comp in self._components.values():
            hook = getattr(comp, "memory_gauges", None)
            if callable(hook):
                try:
                    prefix = type(comp).__name__
                    gauges.update({f"{prefix}.{k}": v for k, v in hook().items()})
                except Exception as e:
                    LOGGER.debug("memory_gauges failed for %s: %s", type(comp).__name__, e)
        return gauges

    def _refresh_pool_refs(self) -> None:
        """Update all pool references after a reconnect."""
        pool = self._db_manager.pool
        self.token_database = pool
        self.channels.pool = pool
        self.analytics.pool = pool
        self.command_configs.pool = pool
        self.redemption_configs.pool = pool
        self.event_configs.pool = pool
        self.timer_configs.pool = pool
        self.message_trigger_configs.pool = pool
        self.video_queue.pool = pool
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
