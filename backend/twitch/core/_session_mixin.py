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

            warmed_channels = self.channels.warm_channel_cache(enabled_channels)  # type: ignore[attr-defined]
            LOGGER.info(f"Warmed channel cache: {warmed_channels} channels")

            total_warmed = 0
            for ch in enabled_channels:
                if ch.channel_id == self._bot_id:  # type: ignore[attr-defined]
                    continue
                await self.subscribe_channel_events(ch.channel_id)  # type: ignore[attr-defined]
                try:
                    await self.redemption_configs.ensure_defaults(  # type: ignore[attr-defined]
                        ch.channel_id,
                        owner_id=self.owner_id,  # type: ignore[attr-defined]
                    )
                    count = await self.command_configs.warm_cache(ch.channel_id)  # type: ignore[attr-defined]
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
                    LOGGER.debug(f"Session already active for channel {channel_id}, skipping")
                    continue

                existing_session = await self.analytics.get_active_session(channel_id)  # type: ignore[attr-defined]
                if existing_session:
                    self._active_sessions[channel_id] = existing_session["id"]  # type: ignore[attr-defined]
                    LOGGER.info(
                        f"Resumed existing session {existing_session['id']} "
                        f"for channel {channel_id}"
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
                    f"Created recovery session {session_id} for live channel {channel_id} "
                    f"(started: {started_at})"
                )

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
                    LOGGER.info(f"Session {sid} created for channel {cid} (poll)")

                for cid in list(self._active_sessions):  # type: ignore[attr-defined]
                    if cid in live_map:
                        continue
                    sid = self._active_sessions.get(cid)  # type: ignore[attr-defined]
                    chatter_data = dict(self._chatter_buffers.get(cid, {}))  # type: ignore[attr-defined]
                    if sid:
                        if chatter_data:
                            try:
                                await self.analytics.flush_chatter_stats(  # type: ignore[attr-defined]
                                    session_id=sid,
                                    channel_id=cid,
                                    chatters=chatter_data,
                                )
                                LOGGER.info(
                                    f"Flushed {len(chatter_data)} chatters for session {sid} (poll)"
                                )
                            except Exception as e:
                                LOGGER.warning(f"Failed to flush chatter stats for {sid}: {e}")
                        try:
                            await self.analytics.end_session(sid, datetime.now(UTC))  # type: ignore[attr-defined]
                            LOGGER.info(f"Session {sid} ended for channel {cid} (poll)")
                        except Exception as e:
                            LOGGER.warning(f"Failed to end session {sid}: {e}")
                    self._active_sessions.pop(cid, None)  # type: ignore[attr-defined]
                    self._chatter_buffers.pop(cid, None)  # type: ignore[attr-defined]
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

    async def _fetch_chatters(self, channel_id: str, token: str) -> list[dict]:
        """Fetch all current chatroom members via /helix/chat/chatters.

        Returns list of {"user_id", "user_login", "user_name"}.
        Paginates automatically; skips on non-200 response.
        """
        viewers: list[dict] = []
        cursor: str | None = None

        async with httpx.AsyncClient(timeout=10.0) as client:
            while True:
                params: dict = {
                    "broadcaster_id": channel_id,
                    "moderator_id": channel_id,
                    "first": 1000,
                }
                if cursor:
                    params["after"] = cursor

                resp = await client.get(
                    "https://api.twitch.tv/helix/chat/chatters",
                    headers={
                        "Client-Id": self._client_id,  # type: ignore[attr-defined]
                        "Authorization": f"Bearer {token}",
                    },
                    params=params,
                )

                if resp.status_code != 200:
                    LOGGER.warning(
                        f"fetch_chatters failed for {channel_id}: "
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
        """Increment watch_seconds for all chatroom viewers every 5 minutes."""
        _interval = 300
        await asyncio.sleep(_interval)

        while True:
            try:
                for channel_id, session_id in list(self._active_sessions.items()):  # type: ignore[attr-defined]
                    try:
                        token_obj = await self.channels.get_token(channel_id)  # type: ignore[attr-defined]
                        if not token_obj:
                            continue

                        viewers = await self._fetch_chatters(channel_id, token_obj.token)
                        if not viewers:
                            continue

                        await self.analytics.increment_watch_seconds(  # type: ignore[attr-defined]
                            session_id=session_id,
                            channel_id=channel_id,
                            viewers=viewers,
                            seconds=_interval,
                        )
                        LOGGER.debug(
                            f"Watch time: +{_interval}s for {len(viewers)} viewers "
                            f"in channel {channel_id}"
                        )
                    except Exception as e:
                        LOGGER.warning(f"Watch time error for channel {channel_id}: {e}")
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
