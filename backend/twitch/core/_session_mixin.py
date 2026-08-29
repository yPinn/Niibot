"""Session lifecycle mixin — stream session recovery, polling, VOD sync.

Extracted from Bot to keep bot.py under 300 lines.
Depends on attributes defined in Bot.__init__:
    self._bot_id, self._subscribed_channels
    self._active_sessions, self._chatter_buffers, self._channel_line_counts
    self.channels, self.analytics
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta

import httpx

LOGGER: logging.Logger = logging.getLogger(__name__)


def _parse_twitch_duration(duration: str) -> timedelta:
    """Parse Twitch VOD duration string (e.g. '3h21m15s') into a timedelta."""
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", duration.strip())
    if not m:
        return timedelta()
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return timedelta(hours=h, minutes=mi, seconds=s)


class _SessionMixin:
    # ------------------------------------------------------------------
    # Startup tasks
    # ------------------------------------------------------------------

    async def _subscribe_initial_channels(self) -> None:
        """Subscribe to EventSub for all enabled channels on startup."""
        try:
            await asyncio.sleep(2)

            enabled_channels = await self.channels.list_enabled_channels()  # type: ignore[attr-defined]
            LOGGER.info(f"Subscribing to {len(enabled_channels)} enabled channels...")

            for ch in enabled_channels:
                if ch.channel_name:
                    self._channel_names[ch.channel_id] = ch.channel_name  # type: ignore[attr-defined]

            warmed_channels = self.channels.warm_channel_cache(enabled_channels)  # type: ignore[attr-defined]
            LOGGER.info(f"Warmed channel cache: {warmed_channels} channels")

            non_bot = [ch for ch in enabled_channels if ch.channel_id != self._bot_id]  # type: ignore[attr-defined]

            # Pre-add to _mod_check_pending before subscribing: asyncio.gather tasks haven't
            # run their first line yet when the event loop yields, so a message arriving in
            # that window would fire a spurious mod-guard notification.
            subscribed_ids: list[str] = []
            for ch in non_bot:
                self._mod_check_pending.add(ch.channel_id)  # type: ignore[attr-defined]
                try:
                    await self.subscribe_channel_events(ch.channel_id)  # type: ignore[attr-defined]
                    subscribed_ids.append(ch.channel_id)
                except Exception as e:
                    LOGGER.error(
                        f"Failed to subscribe channel {ch.channel_name or ch.channel_id}: {e}"
                    )
                    self._mod_check_pending.discard(ch.channel_id)  # type: ignore[attr-defined]

            await asyncio.gather(
                *(self._check_bot_mod_status(cid) for cid in subscribed_ids),  # type: ignore[attr-defined]
                return_exceptions=True,
            )

            total_warmed = 0
            for ch in non_bot:
                total_warmed += await self._seed_and_warm_channel(ch.channel_id)  # type: ignore[attr-defined]

            LOGGER.info(
                f"Initial channel subscription complete — warmed cache: {total_warmed} configs"
            )
        except Exception as e:
            LOGGER.exception(f"Error subscribing to initial channels: {e}")

    async def _recover_active_sessions(self) -> None:
        """Recover sessions for channels that are currently live on bot startup."""
        try:
            await asyncio.sleep(5)

            enabled_channels = await self.channels.list_enabled_channels()  # type: ignore[attr-defined]
            if not enabled_channels:
                return

            channel_ids = [
                ch.channel_id
                for ch in enabled_channels
                if ch.channel_id != self._bot_id  # type: ignore[attr-defined]
            ]
            if not channel_ids:
                return

            LOGGER.info(f"Checking for active streams on {len(channel_ids)} channels...")

            streams = [s async for s in self.fetch_streams(user_ids=channel_ids)]  # type: ignore[attr-defined, arg-type]
            if not streams:
                LOGGER.info("No active streams found during startup recovery")
                return

            LOGGER.info(f"Found {len(streams)} active streams, recovering sessions...")

            for stream in streams:
                channel_id = stream.user.id if stream.user else None
                if not channel_id:
                    continue

                if channel_id in self._active_sessions:  # type: ignore[attr-defined]
                    LOGGER.debug(
                        f"Session already active for channel {self._ch(channel_id)}, skipping"  # type: ignore[attr-defined]
                    )
                    continue

                if channel_id in self._session_creating:  # type: ignore[attr-defined]
                    LOGGER.debug(f"Session creation in-flight for {self._ch(channel_id)}, skipping")  # type: ignore[attr-defined]
                    continue
                self._session_creating.add(channel_id)  # type: ignore[attr-defined]
                try:
                    existing_session = await self.analytics.get_active_session(channel_id)  # type: ignore[attr-defined]
                    if existing_session:
                        self._active_sessions[channel_id] = existing_session["id"]  # type: ignore[attr-defined]
                        LOGGER.info(
                            f"Resumed existing session {existing_session['id']} "
                            f"for channel {self._ch(channel_id)}"  # type: ignore[attr-defined]
                        )
                        continue

                    started_at = stream.started_at or datetime.now(UTC)
                    game_id = str(stream.game_id) if stream.game_id else None

                    session_id = await self.analytics.create_session(  # type: ignore[attr-defined]
                        channel_id=channel_id,
                        started_at=started_at,
                        title=stream.title,
                        game_name=stream.game_name,
                        game_id=game_id,
                    )
                    self._active_sessions[channel_id] = session_id  # type: ignore[attr-defined]
                    LOGGER.info(
                        f"Created recovery session {session_id} for live channel {self._ch(channel_id)} "  # type: ignore[attr-defined]
                        f"(started: {started_at})"
                    )
                finally:
                    self._session_creating.discard(channel_id)  # type: ignore[attr-defined]

            LOGGER.info("Session recovery complete")
            await self._sync_vods_for_channels(channel_ids)  # type: ignore[attr-defined]

        except Exception as e:
            LOGGER.exception(f"Error recovering active sessions: {e}")

    # ------------------------------------------------------------------
    # Background loops
    # ------------------------------------------------------------------

    async def _session_verify_loop(self) -> None:
        """Poll all enabled channels against Twitch API every 3 min."""
        await asyncio.sleep(120)
        _reconcile_ticks = 0
        _reconcile_every = 10  # every 10 * 3 min = 30 min
        while True:
            try:
                enabled = await self.channels.list_enabled_channels()  # type: ignore[attr-defined]
                all_ids = [
                    ch.channel_id
                    for ch in enabled
                    if ch.channel_id != self._bot_id  # type: ignore[attr-defined]
                ]

                if not all_ids:
                    await asyncio.sleep(180)
                    continue

                streams = [s async for s in self.fetch_streams(user_ids=all_ids)]  # type: ignore[attr-defined, arg-type]
                live_map: dict = {}
                if streams:
                    for s in streams:
                        if s.user:
                            live_map[s.user.id] = s

                for cid, stream in live_map.items():
                    if cid in self._active_sessions:  # type: ignore[attr-defined]
                        continue
                    if cid in self._session_creating:  # type: ignore[attr-defined]
                        continue
                    self._session_creating.add(cid)  # type: ignore[attr-defined]
                    try:
                        existing = await self.analytics.get_active_session(cid)  # type: ignore[attr-defined]
                        if existing:
                            self._active_sessions[cid] = existing["id"]  # type: ignore[attr-defined]
                            continue
                        started_at = stream.started_at or datetime.now(UTC)
                        game_id = str(stream.game_id) if stream.game_id else None
                        sid = await self.analytics.create_session(  # type: ignore[attr-defined]
                            channel_id=cid,
                            started_at=started_at,
                            title=stream.title,
                            game_name=stream.game_name,
                            game_id=game_id,
                        )
                        self._active_sessions[cid] = sid  # type: ignore[attr-defined]
                        LOGGER.info(f"[{self._ch(cid)}] Session {sid} created (poll)")  # type: ignore[attr-defined]
                    finally:
                        self._session_creating.discard(cid)  # type: ignore[attr-defined]

                for cid in list(self._active_sessions):  # type: ignore[attr-defined]
                    if cid in live_map:
                        continue
                    sid = self._active_sessions.get(cid)  # type: ignore[attr-defined]
                    # Pop the buffer atomically so a concurrent event_stream_offline flush
                    # gets an empty dict rather than the same data (prevents double-flush).
                    chatter_data = self._chatter_buffers.pop(cid, {})  # type: ignore[attr-defined]
                    if sid:
                        if chatter_data:
                            try:
                                await self.analytics.flush_chatter_stats(  # type: ignore[attr-defined]
                                    session_id=sid,
                                    channel_id=cid,
                                    chatters=chatter_data,
                                )
                                LOGGER.info(
                                    f"[{self._ch(cid)}] Flushed {len(chatter_data)} chatters for session {sid} (poll)"  # type: ignore[attr-defined]
                                )
                            except Exception as e:
                                LOGGER.warning(
                                    f"[{self._ch(cid)}] Failed to flush chatter stats for session {sid}: {e}"  # type: ignore[attr-defined]
                                )
                        try:
                            await self.analytics.end_session(sid, datetime.now(UTC))  # type: ignore[attr-defined]
                            LOGGER.info(f"[{self._ch(cid)}] Session {sid} ended (poll)")  # type: ignore[attr-defined]
                        except Exception as e:
                            LOGGER.warning(f"[{self._ch(cid)}] Failed to end session {sid}: {e}")  # type: ignore[attr-defined]
                    self._active_sessions.pop(cid, None)  # type: ignore[attr-defined]
                    self._channel_line_counts.pop(cid, None)  # type: ignore[attr-defined]

                closed = await self.analytics.close_stale_sessions(max_hours=12)  # type: ignore[attr-defined]
                if closed:
                    LOGGER.info(f"Closed {closed} stale session(s)")

                _reconcile_ticks += 1
                if _reconcile_ticks >= _reconcile_every:
                    await self._reconcile_recent_sessions()  # type: ignore[attr-defined]
                    _reconcile_ticks = 0

            except asyncio.CancelledError:
                break
            except Exception as e:
                LOGGER.warning(f"Session verify error: {e}")
            await asyncio.sleep(180)

    # ------------------------------------------------------------------
    # Watch-time tracking
    # ------------------------------------------------------------------

    async def _fetch_chatters(self, channel_id: str) -> list[dict]:
        """Fetch all current chatroom members via /helix/chat/chatters.

        Uses the bot's own token (master-slave: the bot reads chatters as a
        moderator, so `moderator:read:followers`/`moderator:read:chatters` live
        on the bot, not the broadcaster). Requires the bot to be a mod of the
        channel — a 401/403 is logged and skipped, and self-heals once the bot
        is granted mod.

        Returns list of {"user_id", "user_login", "user_name"}.
        Paginates automatically; skips on non-200 response.
        """
        bot_token = await self.channels.get_token(self._bot_id, "bot")  # type: ignore[attr-defined]
        if not bot_token:
            LOGGER.debug("No bot token, skipping watch time for %s", self._ch(channel_id))  # type: ignore[attr-defined]
            return []

        viewers: list[dict] = []
        cursor: str | None = None

        async with httpx.AsyncClient(timeout=10.0) as client:
            while True:
                params: dict = {
                    "broadcaster_id": channel_id,
                    "moderator_id": self._bot_id,  # type: ignore[attr-defined]
                    "first": 1000,
                }
                if cursor:
                    params["after"] = cursor

                resp = await client.get(
                    "https://api.twitch.tv/helix/chat/chatters",
                    headers={
                        "Client-Id": self._client_id,  # type: ignore[attr-defined]
                        "Authorization": f"Bearer {bot_token.token}",
                    },
                    params=params,
                )

                if resp.status_code != 200:
                    LOGGER.warning(
                        f"fetch_chatters failed for {self._ch(channel_id)}: "  # type: ignore[attr-defined]
                        f"{resp.status_code} {resp.text[:120]}"
                    )
                    break

                data = resp.json()
                viewers.extend(data.get("data", []))
                cursor = data.get("pagination", {}).get("cursor")
                if not cursor:
                    break

        return viewers

    async def _watch_time_loop(self) -> None:
        """Increment watch_seconds for all chatroom viewers every 60 seconds."""
        _interval = 60
        _sem = asyncio.Semaphore(5)
        await asyncio.sleep(_interval)

        async def _process_channel(channel_id: str, session_id: int) -> None:
            viewers = await self._fetch_chatters(channel_id)
            if not viewers:
                return
            async with _sem:
                await self.analytics.increment_watch_seconds(  # type: ignore[attr-defined]
                    session_id=session_id,
                    channel_id=channel_id,
                    viewers=viewers,
                    seconds=_interval,
                )
            LOGGER.debug(
                f"Watch time: +{_interval}s for {len(viewers)} viewers in channel {self._ch(channel_id)}"  # type: ignore[attr-defined]
            )

        while True:
            try:
                channels = list(self._active_sessions.items())  # type: ignore[attr-defined]
                results = await asyncio.gather(
                    *[_process_channel(cid, sid) for cid, sid in channels],
                    return_exceptions=True,
                )
                for (cid, _), exc in zip(channels, results, strict=True):
                    if isinstance(exc, asyncio.CancelledError):
                        raise exc
                    if isinstance(exc, Exception):
                        LOGGER.warning(f"Watch time error for channel {self._ch(cid)}: {exc}")  # type: ignore[attr-defined]
            except asyncio.CancelledError:
                break
            except Exception as e:
                LOGGER.warning(f"Watch time loop error: {e}")

            await asyncio.sleep(_interval)

    # ------------------------------------------------------------------
    # VOD reconciliation
    # ------------------------------------------------------------------

    async def _reconcile_recent_sessions(self) -> None:
        """Use Twitch VOD data to fix session durations."""
        try:
            enabled_channels = await self.channels.list_enabled_channels()  # type: ignore[attr-defined]
            if not enabled_channels:
                return

            for ch in enabled_channels:
                if ch.channel_id == self._bot_id:  # type: ignore[attr-defined]
                    continue
                try:
                    vods = []
                    async for v in self.fetch_videos(  # type: ignore[attr-defined]
                        user_id=ch.channel_id,
                        type="archive",
                        first=5,
                    ):
                        if v.created_at and v.duration:
                            vods.append(
                                {
                                    "started_at": v.created_at,
                                    "ended_at": v.created_at + v.duration,  # type: ignore[operator]
                                }
                            )

                    updated = await self.analytics.reconcile_sessions_with_vods(  # type: ignore[attr-defined]
                        ch.channel_id, vods
                    )
                    if updated:
                        LOGGER.info(
                            f"Reconciled {updated} session(s) for channel {ch.channel_name or ch.channel_id}"
                        )
                except Exception as e:
                    LOGGER.debug(
                        f"VOD reconcile failed for {ch.channel_name or ch.channel_id}: {e}"
                    )
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
                    synced_count = 0
                    async for video in self.fetch_videos(  # type: ignore[attr-defined]
                        user_id=channel_id,
                        type="archive",
                        first=limit_per_channel,
                    ):
                        started_at = video.created_at
                        if not started_at:
                            continue

                        duration = video.duration
                        if duration:
                            ended_at = started_at + _parse_twitch_duration(duration)
                        else:
                            ended_at = started_at

                        session_id = await self.analytics.sync_session_from_vod(  # type: ignore[attr-defined]
                            channel_id=channel_id,
                            started_at=started_at,
                            ended_at=ended_at,
                            title=video.title,
                        )

                        if session_id:
                            synced_count += 1
                            total_synced += 1

                    if synced_count > 0:
                        LOGGER.info(
                            f"Synced {synced_count} VODs for channel {self._ch(channel_id)}"  # type: ignore[attr-defined]
                        )

                except Exception as e:
                    LOGGER.warning(f"Failed to sync VODs for channel {self._ch(channel_id)}: {e}")  # type: ignore[attr-defined]
                    continue

            if total_synced > 0:
                LOGGER.info(f"VOD sync complete: {total_synced} new sessions imported")
            else:
                LOGGER.info("VOD sync complete: all sessions already up to date")

        except Exception as e:
            LOGGER.exception(f"Error during VOD sync: {e}")
