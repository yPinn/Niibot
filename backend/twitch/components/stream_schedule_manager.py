"""Stream schedule auto-apply — title/game switching driven by StreamScheduleService.

Two triggers call the same `resolve_for_channel`, so they can never disagree
(see shared/services/stream_schedule_service.py):

- `event_stream_online`: resolves and applies immediately on go-live.
- `_poll_loop`: every 60s, for currently-live channels only (mirrors
  timer_manager.py's pattern), re-resolves and re-applies only when the
  active segment actually changed — avoids hammering modify_channel every tick.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import twitchio
from twitchio.ext import commands, routines

from shared.repositories.stream_schedule import StreamScheduleRepository
from shared.services.stream_schedule_service import StreamScheduleService
from utils.reauth import is_scope_error
from utils.substitution import substitute_variables

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER: logging.Logger = logging.getLogger(__name__)


class _NoChatter:
    """Minimal chatter stub for title-template substitution (no user context)."""

    display_name: str | None = None
    name: str | None = None


class StreamScheduleManagerComponent(commands.Component):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.service = StreamScheduleService(StreamScheduleRepository(bot.token_database))
        # channel_id -> segment id last applied, so the poll only calls the API
        # again when the resolved segment actually changes.
        self._last_applied_segment: dict[str, int] = {}

    def refresh_pool(self, pool) -> None:
        self.service = StreamScheduleService(StreamScheduleRepository(pool))

    async def component_load(self) -> None:
        self._poll_loop.start()
        LOGGER.info("StreamScheduleManager component loaded")

    async def component_teardown(self) -> None:
        # cancel(), not stop(): stop() blocks teardown for up to one interval (60s).
        self._poll_loop.cancel()
        LOGGER.info("StreamScheduleManager component unloaded")

    def memory_gauges(self) -> dict[str, int]:
        return {"stream_schedule_last_applied": len(self._last_applied_segment)}

    @commands.Component.listener()
    async def event_stream_online(self, payload: twitchio.StreamOnline) -> None:
        channel_id = payload.broadcaster.id
        await self._apply_if_changed(channel_id, force=True)

    @routines.routine(delta=timedelta(seconds=60), wait_first=True)
    async def _poll_loop(self) -> None:
        for channel_id in self.bot.sessions.live_channels:
            await self._apply_if_changed(channel_id, force=False)

    async def _apply_if_changed(self, channel_id: str, *, force: bool) -> None:
        try:
            resolved = await self.service.resolve_for_channel(channel_id, datetime.now(UTC))
        except Exception as e:
            LOGGER.warning(f"[{self.bot._ch(channel_id)}] Stream schedule resolve failed: {e}")  # type: ignore[attr-defined]
            return

        if resolved is None:
            # Nothing scheduled right now (or not any more) — stop tracking so a
            # later schedule with the same segment id isn't skipped as "unchanged".
            self._last_applied_segment.pop(channel_id, None)
            return

        segment = resolved.segment
        if not force and self._last_applied_segment.get(channel_id) == segment.id:
            return

        kwargs: dict[str, str] = {}
        if segment.title_template:
            channel_record = await self.bot.channels.get_channel(channel_id)
            channel_name = channel_record.channel_name if channel_record else channel_id
            title = substitute_variables(segment.title_template, _NoChatter(), channel_name, "")
            if title:
                kwargs["title"] = title
        if segment.game_id:
            kwargs["game_id"] = segment.game_id

        if not kwargs:
            # Segment defines neither a title nor a game — nothing to apply, but
            # still record it so the poll doesn't retry every tick.
            self._last_applied_segment[channel_id] = segment.id
            return

        try:
            users = await self.bot.fetch_users(ids=[channel_id])
            if not users:
                LOGGER.warning(f"[{self.bot._ch(channel_id)}] Could not fetch broadcaster")  # type: ignore[attr-defined]
                return
            await users[0].modify_channel(**kwargs)
            self._last_applied_segment[channel_id] = segment.id
            LOGGER.info(
                f"[{self.bot._ch(channel_id)}] Applied schedule segment {segment.id}: {kwargs}"  # type: ignore[attr-defined]
            )
        except Exception as e:
            if is_scope_error(e):
                await self.bot._mark_reauth_required(channel_id)  # type: ignore[attr-defined]
                return
            LOGGER.warning(f"[{self.bot._ch(channel_id)}] Schedule apply failed: {e}")  # type: ignore[attr-defined]


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(StreamScheduleManagerComponent(bot))  # type: ignore[arg-type]


async def teardown(bot: commands.Bot) -> None: ...
