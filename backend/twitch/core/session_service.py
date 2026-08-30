"""Stream-session ownership for the bot.

Owns the per-channel session state that used to live loose on ``Bot`` and be
mutated from three separate places (the stream_online/offline component
listeners, the 3-minute verify poll, and the new-token handler):

- ``_active``        — channel id → analytics session id (live now)
- ``_creating``      — channel ids mid-create (single-flight lock)
- ``_buffers``       — channel id → {chatter_id: {...}} chat-activity buffer
- ``_line_counts``   — channel id → cumulative line count this session

``ensure_session`` / ``end_session`` are the single implementations every path
routes through. Background loops (recover, verify, watch-time) are owned here
and driven by ``start()`` / ``stop()``.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

import httpx

if TYPE_CHECKING:
    from core.subscription_manager import SubscriptionManager
    from shared.repositories.analytics import AnalyticsRepository
    from shared.repositories.channel import ChannelRepository

LOGGER: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ChatterSnapshot:
    """A complete chatters response, or an explicit failed observation."""

    viewers: list[dict]
    complete: bool


def parse_twitch_duration(duration: str) -> timedelta:
    """Parse a Twitch VOD duration string (e.g. '3h21m15s') into a timedelta."""
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", duration.strip())
    if not m:
        return timedelta()
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return timedelta(hours=h, minutes=mi, seconds=s)


class _StreamClient(Protocol):
    """The subset of twitchio the service needs — the Bot satisfies this."""

    def fetch_streams(self, *, user_ids: list[str]) -> Any: ...
    def fetch_videos(self, *, user_id: str, type: str, first: int) -> Any: ...


class SessionService:
    _VERIFY_INTERVAL = 180
    _WATCH_INTERVAL = 60
    _RECONCILE_EVERY = 10  # verify ticks between VOD reconciliations (~30 min)

    def __init__(
        self,
        *,
        analytics: AnalyticsRepository,
        channels: ChannelRepository,
        subs: SubscriptionManager,
        client: _StreamClient,
        bot_id: str,
        client_id: str,
    ) -> None:
        self._analytics = analytics
        self._channels = channels
        self._subs = subs
        self._client = client
        self._bot_id = bot_id
        self._client_id = client_id

        self._active: dict[str, int] = {}
        self._creating: set[str] = set()
        self._buffers: dict[str, dict[str, dict]] = {}
        self._line_counts: dict[str, int] = {}
        self._tasks: set[asyncio.Task] = set()

    def _ch(self, channel_id: str) -> str:
        return self._subs.ch(channel_id)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def session_id(self, channel_id: str) -> int | None:
        return self._active.get(channel_id)

    def is_live(self, channel_id: str) -> bool:
        return channel_id in self._active

    def line_count(self, channel_id: str) -> int:
        return self._line_counts.get(channel_id, 0)

    @property
    def live_channels(self) -> frozenset[str]:
        return frozenset(self._active)

    # ------------------------------------------------------------------
    # Hot path — one call per chat message
    # ------------------------------------------------------------------

    def record_line(
        self, channel_id: str, chatter_id: str, username: str, display_name: str | None
    ) -> None:
        """Record chat activity for the active session; no-op when not live."""
        if channel_id not in self._active:
            return
        buf = self._buffers.setdefault(channel_id, {})
        entry = buf.get(chatter_id)
        now = datetime.now(UTC)
        if entry:
            entry["count"] += 1
            entry["last_at"] = now
            entry["username"] = username
            entry["display_name"] = display_name
        else:
            buf[chatter_id] = {
                "username": username,
                "display_name": display_name,
                "count": 1,
                "last_at": now,
            }
        self._line_counts[channel_id] = self._line_counts.get(channel_id, 0) + 1

    # ------------------------------------------------------------------
    # Lifecycle — the single create / end implementations
    # ------------------------------------------------------------------

    async def ensure_session(
        self, channel_id: str, *, stream: Any | None = None, create_if_offline: bool = False
    ) -> int | None:
        """Idempotently attach an analytics session to a live channel.

        Resumes an existing DB session, else creates one. ``stream`` is the
        twitchio Stream when the caller already has it; otherwise it is fetched.
        When the channel is not actually live, a session is created only if
        ``create_if_offline`` is set (the stream_online path, where EventSub is
        authoritative and the Helix fetch may just be lagging).
        """
        if channel_id in self._active:
            return self._active[channel_id]
        if channel_id in self._creating:
            return None

        self._creating.add(channel_id)
        try:
            existing = await self._analytics.get_active_session(channel_id)
            if existing:
                self._active[channel_id] = existing["id"]
                LOGGER.info(f"[{self._ch(channel_id)}] Resumed session {existing['id']}")
                return existing["id"]

            if stream is None:
                stream = await self._fetch_stream(channel_id)
            if stream is None and not create_if_offline:
                return None

            started_at = getattr(stream, "started_at", None) or datetime.now(UTC)
            game_id = getattr(stream, "game_id", None)
            session_id = await self._analytics.create_session(
                channel_id=channel_id,
                started_at=started_at,
                title=getattr(stream, "title", None),
                game_name=getattr(stream, "game_name", None),
                game_id=str(game_id) if game_id else None,
            )
            self._active[channel_id] = session_id
            LOGGER.info(f"[{self._ch(channel_id)}] Session {session_id} created")
            return session_id
        finally:
            self._creating.discard(channel_id)

    async def end_session(self, channel_id: str) -> None:
        """Flush the chatter buffer, close the session, refresh overlap.

        Always clears the per-channel buffers even when no session is tracked,
        so a stale buffer can't leak into the next session.
        """
        session_id = self._active.get(channel_id)
        chatter_data = self._buffers.pop(channel_id, {})
        self._line_counts.pop(channel_id, None)
        if session_id is None:
            return

        if chatter_data:
            try:
                await self._analytics.flush_chatter_stats(
                    session_id=session_id, channel_id=channel_id, chatters=chatter_data
                )
                LOGGER.info(
                    f"[{self._ch(channel_id)}] Flushed {len(chatter_data)} chatters "
                    f"for session {session_id}"
                )
            except Exception as e:
                LOGGER.warning(
                    f"[{self._ch(channel_id)}] Failed to flush chatter stats "
                    f"for session {session_id}: {e}"
                )

        ended_at = datetime.now(UTC)
        for attempt in range(3):
            try:
                await self._analytics.end_session(session_id, ended_at)
                break
            except Exception as e:
                if attempt < 2:
                    LOGGER.warning(
                        f"[{self._ch(channel_id)}] end_session attempt {attempt + 1}/3 failed: {e}"
                    )
                    await asyncio.sleep(2)
                else:
                    LOGGER.error(
                        f"[{self._ch(channel_id)}] Failed to end session {session_id} "
                        "after 3 attempts"
                    )

        self._active.pop(channel_id, None)
        LOGGER.info(f"[{self._ch(channel_id)}] Session {session_id} ended")
        self._fire_refresh_overlap(channel_id)

    def _fire_refresh_overlap(self, channel_id: str) -> None:
        if not hasattr(self._analytics, "refresh_overlap"):
            return
        task = asyncio.create_task(self._analytics.refresh_overlap(channel_id))
        self._tasks.add(task)

        def _log_err(t: asyncio.Task) -> None:
            self._tasks.discard(t)
            if not t.cancelled() and t.exception():
                LOGGER.warning(f"[{self._ch(channel_id)}] Overlap refresh failed: {t.exception()}")

        task.add_done_callback(_log_err)

    # ------------------------------------------------------------------
    # EventSub entry points (Bot delegates its listeners here)
    # ------------------------------------------------------------------

    async def on_stream_online(self, channel_id: str) -> None:
        if channel_id in self._active:
            LOGGER.debug(f"[{self._ch(channel_id)}] Stream online: session already active")
            return
        stream = None
        for attempt in range(4):
            stream = await self._fetch_stream(channel_id)
            if stream is not None:
                break
            if attempt < 3:
                await asyncio.sleep(3)
        await self.ensure_session(channel_id, stream=stream, create_if_offline=True)

    async def on_stream_offline(self, channel_id: str) -> None:
        if channel_id not in self._active and channel_id not in self._buffers:
            LOGGER.warning(f"[{self._ch(channel_id)}] Stream offline: no active session")
            return
        await self.end_session(channel_id)

    async def _fetch_stream(self, channel_id: str) -> Any | None:
        async for s in self._client.fetch_streams(user_ids=[channel_id]):
            return s
        return None

    # ------------------------------------------------------------------
    # Background loops
    # ------------------------------------------------------------------

    def start(self) -> None:
        for coro in (self._recover_loop(), self._verify_loop(), self._watch_time_loop()):
            task = asyncio.create_task(coro)
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def stop(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()

    async def _enabled_channel_ids(self) -> list[str]:
        enabled = await self._channels.list_enabled_channels()
        return [ch.channel_id for ch in enabled if ch.channel_id != self._bot_id]

    async def _recover_loop(self) -> None:
        """On startup, attach sessions for channels that are already live."""
        try:
            await asyncio.sleep(5)
            channel_ids = await self._enabled_channel_ids()
            if not channel_ids:
                return

            LOGGER.info(f"Checking for active streams on {len(channel_ids)} channels...")
            streams = [s async for s in self._client.fetch_streams(user_ids=channel_ids)]
            if not streams:
                LOGGER.info("No active streams found during startup recovery")
            else:
                LOGGER.info(f"Found {len(streams)} active streams, recovering sessions...")
                for stream in streams:
                    channel_id = stream.user.id if stream.user else None
                    if channel_id:
                        await self.ensure_session(channel_id, stream=stream, create_if_offline=True)
                LOGGER.info("Session recovery complete")

            await self._sync_vods(channel_ids)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            LOGGER.exception(f"Error recovering active sessions: {e}")

    async def _verify_loop(self) -> None:
        """Poll enabled channels against Helix every 3 min — the EventSub fallback."""
        await asyncio.sleep(120)
        reconcile_ticks = 0
        while True:
            try:
                all_ids = await self._enabled_channel_ids()
                if not all_ids:
                    await asyncio.sleep(self._VERIFY_INTERVAL)
                    continue

                streams = [s async for s in self._client.fetch_streams(user_ids=all_ids)]
                live_map = {s.user.id: s for s in streams if s.user}

                for cid, stream in live_map.items():
                    await self.ensure_session(cid, stream=stream, create_if_offline=True)

                for cid in list(self._active):
                    if cid not in live_map:
                        await self.end_session(cid)

                closed = await self._analytics.close_stale_sessions(max_hours=12)
                if closed:
                    LOGGER.info(f"Closed {closed} stale session(s)")

                reconcile_ticks += 1
                if reconcile_ticks >= self._RECONCILE_EVERY:
                    await self._reconcile_recent_sessions()
                    reconcile_ticks = 0
            except asyncio.CancelledError:
                break
            except Exception as e:
                LOGGER.warning(f"Session verify error: {e}")
            await asyncio.sleep(self._VERIFY_INTERVAL)

    async def _watch_time_loop(self) -> None:
        """Increment watch_seconds for every chatroom viewer every 60 seconds."""
        sem = asyncio.Semaphore(5)
        await asyncio.sleep(self._WATCH_INTERVAL)

        async def _process(channel_id: str, session_id: int) -> None:
            snapshot = await self._fetch_chatters(channel_id)
            if not snapshot.complete:
                return
            async with sem:
                recorded = await self._analytics.record_attendance_snapshot(
                    session_id=session_id,
                    channel_id=channel_id,
                    viewers=snapshot.viewers,
                    seconds=self._WATCH_INTERVAL,
                )
            if not recorded:
                LOGGER.debug(
                    "Skipped snapshot for inactive session %s in channel %s",
                    session_id,
                    self._ch(channel_id),
                )
                return
            LOGGER.debug(
                f"Watch time: +{self._WATCH_INTERVAL}s for {len(snapshot.viewers)} viewers "
                f"in channel {self._ch(channel_id)}"
            )

        while True:
            try:
                channels = list(self._active.items())
                results = await asyncio.gather(
                    *(_process(cid, sid) for cid, sid in channels),
                    return_exceptions=True,
                )
                for (cid, _), exc in zip(channels, results, strict=True):
                    if isinstance(exc, asyncio.CancelledError):
                        raise exc
                    if isinstance(exc, Exception):
                        LOGGER.warning(f"Watch time error for channel {self._ch(cid)}: {exc}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                LOGGER.warning(f"Watch time loop error: {e}")
            await asyncio.sleep(self._WATCH_INTERVAL)

    async def _fetch_chatters(self, channel_id: str) -> ChatterSnapshot:
        """Fetch all chatters, distinguishing a complete empty result from failure."""
        bot_token = await self._channels.get_token(self._bot_id, "bot")
        if not bot_token:
            LOGGER.debug("No bot token, skipping watch time for %s", self._ch(channel_id))
            return ChatterSnapshot(viewers=[], complete=False)

        viewers: list[dict] = []
        cursor: str | None = None
        async with httpx.AsyncClient(timeout=10.0) as client:
            while True:
                params: dict = {
                    "broadcaster_id": channel_id,
                    "moderator_id": self._bot_id,
                    "first": 1000,
                }
                if cursor:
                    params["after"] = cursor
                resp = await client.get(
                    "https://api.twitch.tv/helix/chat/chatters",
                    headers={
                        "Client-Id": self._client_id,
                        "Authorization": f"Bearer {bot_token.token}",
                    },
                    params=params,
                )
                if resp.status_code != 200:
                    LOGGER.warning(
                        f"fetch_chatters failed for {self._ch(channel_id)}: "
                        f"{resp.status_code} {resp.text[:120]}"
                    )
                    return ChatterSnapshot(viewers=[], complete=False)
                data = resp.json()
                viewers.extend(data.get("data", []))
                cursor = data.get("pagination", {}).get("cursor")
                if not cursor:
                    break
        return ChatterSnapshot(viewers=viewers, complete=True)

    # ------------------------------------------------------------------
    # VOD reconciliation
    # ------------------------------------------------------------------

    async def _reconcile_recent_sessions(self) -> None:
        """Use Twitch VOD data to fix recent session durations."""
        try:
            enabled_channels = await self._channels.list_enabled_channels()
            for ch in enabled_channels:
                if ch.channel_id == self._bot_id:
                    continue
                try:
                    vods = []
                    async for v in self._client.fetch_videos(
                        user_id=ch.channel_id, type="archive", first=5
                    ):
                        if v.created_at and v.duration:
                            vods.append(
                                {"started_at": v.created_at, "ended_at": v.created_at + v.duration}
                            )
                    updated = await self._analytics.reconcile_sessions_with_vods(
                        ch.channel_id, vods
                    )
                    if updated:
                        LOGGER.info(
                            f"Reconciled {updated} session(s) for "
                            f"channel {ch.channel_name or ch.channel_id}"
                        )
                except Exception as e:
                    LOGGER.debug(
                        f"VOD reconcile failed for {ch.channel_name or ch.channel_id}: {e}"
                    )
        except Exception as e:
            LOGGER.warning(f"Session reconciliation error: {e}")

    async def _sync_vods(self, channel_ids: list[str], limit_per_channel: int = 20) -> None:
        """Import historical VODs from Twitch as past sessions."""
        try:
            LOGGER.info(f"Starting VOD sync for {len(channel_ids)} channels...")
            total_synced = 0
            for channel_id in channel_ids:
                try:
                    synced_count = 0
                    async for video in self._client.fetch_videos(
                        user_id=channel_id, type="archive", first=limit_per_channel
                    ):
                        started_at = video.created_at
                        if not started_at:
                            continue
                        ended_at = (
                            started_at + parse_twitch_duration(video.duration)
                            if video.duration
                            else started_at
                        )
                        session_id = await self._analytics.sync_session_from_vod(
                            channel_id=channel_id,
                            started_at=started_at,
                            ended_at=ended_at,
                            title=video.title,
                        )
                        if session_id:
                            synced_count += 1
                            total_synced += 1
                    if synced_count:
                        LOGGER.info(
                            f"Synced {synced_count} VODs for channel {self._ch(channel_id)}"
                        )
                except Exception as e:
                    LOGGER.warning(f"Failed to sync VODs for channel {self._ch(channel_id)}: {e}")
                    continue
            if total_synced:
                LOGGER.info(f"VOD sync complete: {total_synced} new sessions imported")
            else:
                LOGGER.info("VOD sync complete: all sessions already up to date")
        except Exception as e:
            LOGGER.exception(f"Error during VOD sync: {e}")
