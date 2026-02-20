"""Timer manager component — sends scheduled messages during active streams."""

from __future__ import annotations

import asyncio
import logging
import random
import re
from datetime import datetime
from typing import TYPE_CHECKING

from twitchio.ext import commands

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER = logging.getLogger("TimerManager")

_RANDOM_PATTERN = re.compile(r"\$\(random\s+(\d+)\s*,\s*(\d+)\)")
_PICK_PATTERN = re.compile(r"\$\(pick\s+(.+?)\)")


def _render_message(template: str, channel_name: str) -> str:
    """Substitute supported variables in a timer message template.

    Supported: $(channel), $(random min,max), $(pick a,b,c)
    $(user) and $(query) are not applicable for timers and are left as-is.
    """
    text = template.replace("$(channel)", channel_name)

    def _random_replace(m: re.Match) -> str:
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo > hi:
            lo, hi = hi, lo
        return str(random.randint(lo, hi))

    text = _RANDOM_PATTERN.sub(_random_replace, text)

    def _pick_replace(m: re.Match) -> str:
        items = [i.strip() for i in m.group(1).split(",") if i.strip()]
        return random.choice(items) if items else ""

    text = _PICK_PATTERN.sub(_pick_replace, text)
    return text


class TimerManagerComponent(commands.Component):
    """Background component that polls timers every 60 seconds and fires them
    when both the time interval and minimum chat-line threshold are satisfied.

    Timers only fire during active live streams (_active_sessions).
    """

    COMMANDS: list[dict] = []

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        # timer_id → datetime of last fire
        self._timer_last_fire: dict[int, datetime] = {}
        # timer_id → channel line count snapshot at last fire
        self._timer_last_fire_lines: dict[int, int] = {}

    async def component_load(self) -> None:
        asyncio.create_task(self._timer_poll_loop())
        LOGGER.info("TimerManagerComponent loaded, poll loop started")

    async def _timer_poll_loop(self) -> None:
        """Main poll loop: checks all channels every 60 seconds."""
        while True:
            await asyncio.sleep(60)
            now = datetime.now()

            for channel_id in list(self.bot._subscribed_channels):
                if channel_id not in self.bot._active_sessions:
                    continue  # Only during live streams

                try:
                    timers = await self.bot.timer_configs.list_enabled(channel_id)
                except Exception as e:
                    LOGGER.warning(f"Failed to load timers for {channel_id}: {e}")
                    continue

                for timer in timers:
                    # --- Time gate ---
                    last_fire = self._timer_last_fire.get(timer.id)
                    if last_fire is not None:
                        elapsed = (now - last_fire).total_seconds()
                        if elapsed < timer.interval_seconds:
                            continue

                    # --- Chat-line gate ---
                    current_lines = self.bot._channel_line_counts.get(channel_id, 0)
                    lines_at_last = self._timer_last_fire_lines.get(timer.id, 0)
                    if current_lines - lines_at_last < timer.min_lines:
                        continue

                    await self._fire_timer(channel_id, timer, current_lines, now)

    async def _fire_timer(self, channel_id: str, timer, current_lines: int, now: datetime) -> None:
        """Send the timer message and record the fire time/line snapshot."""
        try:
            channel_record = await self.bot.channels.get_channel(channel_id)
            channel_name = channel_record.channel_name if channel_record else None
            if not channel_name:
                LOGGER.warning(
                    f"Timer '{timer.timer_name}': could not resolve channel name for {channel_id}"
                )
                return

            message = _render_message(timer.message_template, channel_name)
            twitch_channel = self.bot.get_channel(channel_name)
            if not twitch_channel:
                LOGGER.warning(
                    f"Timer '{timer.timer_name}': channel '{channel_name}' not in bot cache"
                )
                return

            await twitch_channel.send(message)
            self._timer_last_fire[timer.id] = now
            self._timer_last_fire_lines[timer.id] = current_lines
            LOGGER.info(f"Timer '{timer.timer_name}' fired in #{channel_name}")

        except Exception as e:
            LOGGER.error(f"Timer '{timer.timer_name}' fire failed: {e}")
