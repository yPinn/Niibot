"""Timer manager component — sends scheduled messages during active streams."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import twitchio
import twitchio.ext.commands as commands
import twitchio.ext.routines as routines

from shared.builtin_timers import BUILTIN_TIMERS, BuiltinTimerDef
from utils.substitution import substitute_variables

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER: logging.Logger = logging.getLogger(__name__)


class _NoChatter:
    """Minimal chatter stub for timer substitution (no user context)."""

    display_name: str | None = None
    name: str | None = None


def _still_on_interval(last_fire: datetime | None, now: datetime, interval_seconds: int) -> bool:
    """True if interval_seconds hasn't elapsed since last_fire (i.e. too soon to fire again)."""
    if last_fire is None:
        return False
    return (now - last_fire).total_seconds() < interval_seconds


class TimerManagerComponent(commands.Component):
    """Background component that polls timers every 60 seconds and fires them
    when both the time interval and minimum chat-line threshold are satisfied.

    Timers only fire during active live streams (bot.sessions.live_channels).
    """

    COMMANDS: list[dict] = []

    # Sweep for deleted-timer/unsubscribed-channel fire-state every N polls
    # (~30 min at the 60s cadence) rather than every tick — a full
    # all-subscribed-channels DB pass every 60s would be wasteful, and these
    # dicts only grow slowly (one entry per timer/channel ever seen).
    _PRUNE_INTERVAL_POLLS = 30

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        # timer_id → datetime of last fire (DB timers)
        self._timer_last_fire: dict[int, datetime] = {}
        # timer_id → channel line count snapshot at last fire (DB timers)
        self._timer_last_fire_lines: dict[int, int] = {}
        # (channel_id, timer_name) → datetime of last fire (builtin timers)
        self._builtin_last_fire: dict[tuple[str, str], datetime] = {}
        # (channel_id, timer_name) → line count snapshot at last fire (builtin timers)
        self._builtin_last_fire_lines: dict[tuple[str, str], int] = {}
        self._poll_count = 0

    async def component_load(self) -> None:
        self._timer_poll_loop.start()
        LOGGER.info("TimerManager component loaded")

    async def component_teardown(self) -> None:
        # cancel(), not stop(): stop() blocks teardown for up to one interval (60s).
        self._timer_poll_loop.cancel()
        LOGGER.info("TimerManager component unloaded")

    def memory_gauges(self) -> dict[str, int]:
        return {
            "timer_last_fire": len(self._timer_last_fire),
            "builtin_last_fire": len(self._builtin_last_fire),
        }

    @routines.routine(delta=timedelta(seconds=60), wait_first=True)
    async def _timer_poll_loop(self) -> None:
        """Main poll loop: checks all channels every 60 seconds."""
        now = datetime.now(UTC)

        subscribed = self.bot.subs.subscribed
        live = self.bot.sessions.live_channels
        live_channels = [c for c in subscribed if c in live]
        LOGGER.debug(
            f"[timer-poll] subscribed={len(subscribed)} "
            f"live={len(live_channels)} active_sessions={sorted(live)}"
        )

        for channel_id in subscribed:
            if channel_id not in live:
                continue  # Only during live streams

            if channel_id not in self.bot._bot_is_mod:  # type: ignore[attr-defined]
                continue  # Bot must be mod to send timer messages

            try:
                timers = await self.bot.timer_configs.list_enabled(channel_id)
            except Exception as e:
                LOGGER.warning(f"Failed to load timers for {channel_id}: {e}")
                continue

            current_lines = self.bot.sessions.line_count(channel_id)
            LOGGER.debug(
                f"[timer-poll] channel={channel_id} enabled_timers={len(timers)} "
                f"line_count={current_lines}"
            )

            for timer in timers:
                # --- Time gate ---
                last_fire = self._timer_last_fire.get(timer.id)
                if _still_on_interval(last_fire, now, timer.interval_seconds):
                    LOGGER.debug(f"[timer-poll] '{timer.timer_name}' skip: time")
                    continue

                # --- Chat-line gate ---
                lines_at_last = self._timer_last_fire_lines.get(timer.id, 0)
                delta_lines = current_lines - lines_at_last
                if delta_lines < timer.min_lines:
                    LOGGER.debug(
                        f"[timer-poll] '{timer.timer_name}' skip: min_lines "
                        f"({delta_lines}/{timer.min_lines})"
                    )
                    continue

                await self._fire_timer(channel_id, timer, current_lines, now)

            # --- Builtin timers (skipped if DB has a timer with the same name) ---
            db_timer_names = {t.timer_name for t in timers}
            for bt in BUILTIN_TIMERS:
                if bt.timer_name in db_timer_names:
                    continue
                bkey = (channel_id, bt.timer_name)
                last_fire = self._builtin_last_fire.get(bkey)
                if _still_on_interval(last_fire, now, bt.interval_seconds):
                    continue
                lines_at_last = self._builtin_last_fire_lines.get(bkey, 0)
                if current_lines - lines_at_last < bt.min_lines:
                    continue
                await self._fire_builtin_timer(channel_id, bt, current_lines, now, bkey)

        self._poll_count += 1
        if self._poll_count % self._PRUNE_INTERVAL_POLLS == 0:
            await self._prune_stale_timer_state(subscribed)

    async def _prune_stale_timer_state(self, subscribed_channels: frozenset[str]) -> None:
        """Drop fire-state for timers/channels that no longer exist.

        Without this, `_timer_last_fire`/`_timer_last_fire_lines` (keyed by
        DB timer id) and the builtin equivalents (keyed by channel_id) grow
        for as long as the process runs — a deleted timer or unsubscribed
        channel's entry is never otherwise removed.
        """
        valid_timer_ids: set[int] = set()
        for channel_id in subscribed_channels:
            try:
                timers = await self.bot.timer_configs.list_enabled(channel_id)
            except Exception as e:
                # Can't tell which timer ids are still valid without a full
                # sweep — skip pruning this round rather than risk dropping
                # state for a channel we just failed to query.
                LOGGER.warning(
                    f"[timer-prune] Failed to load timers for {channel_id}, skipping this round: {e}"
                )
                return
            valid_timer_ids.update(t.id for t in timers)

        stale_ids = [tid for tid in self._timer_last_fire if tid not in valid_timer_ids]
        for tid in stale_ids:
            self._timer_last_fire.pop(tid, None)
            self._timer_last_fire_lines.pop(tid, None)

        stale_bkeys = [
            bkey for bkey in self._builtin_last_fire if bkey[0] not in subscribed_channels
        ]
        for bkey in stale_bkeys:
            self._builtin_last_fire.pop(bkey, None)
            self._builtin_last_fire_lines.pop(bkey, None)

        if stale_ids or stale_bkeys:
            LOGGER.info(
                f"[timer-prune] Dropped {len(stale_ids)} timer + {len(stale_bkeys)} builtin fire-state entries"
            )

    @commands.Component.listener()
    async def event_message(self, message: twitchio.ChatMessage) -> None:
        """Handle timer alias commands — e.g. !socials fires the timer immediately.

        Option B: manual trigger also resets the interval countdown so the timer
        won't auto-fire again until another full interval has passed.
        """
        if not message.text or not message.text.startswith("!"):
            return
        cmd_name = message.text.split(None, 1)[0][1:].lower()
        if not cmd_name:
            return

        if not message.broadcaster:
            return
        channel_id = message.broadcaster.id
        if not channel_id:
            return

        if channel_id not in self.bot._bot_is_mod:  # type: ignore[attr-defined]
            return

        try:
            timers = await self.bot.timer_configs.list_enabled(channel_id)
        except Exception as e:
            LOGGER.warning(f"Alias lookup failed for channel {channel_id}: {e}")
            return

        for timer in timers:
            if timer.command_alias and timer.command_alias.lower() == cmd_name:
                now = datetime.now(UTC)
                last_fire = self._timer_last_fire.get(timer.id)
                if _still_on_interval(last_fire, now, timer.interval_seconds):
                    return
                current_lines = self.bot.sessions.line_count(channel_id)
                await self._fire_timer(channel_id, timer, current_lines, now)
                break

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

            message = substitute_variables(timer.message_template, _NoChatter(), channel_name, "")

            users = await self.bot.fetch_users(ids=[channel_id])
            if not users:
                LOGGER.warning(
                    f"Timer '{timer.timer_name}': could not fetch broadcaster for {channel_id}"
                )
                return

            sender_id = self.bot.sender_for(channel_id)
            if timer.announce:
                await users[0].send_announcement(
                    message=message,
                    moderator=sender_id,
                    color="primary",
                )
            else:
                await users[0].send_message(
                    message=message,
                    sender=sender_id,
                )
            self._timer_last_fire[timer.id] = now
            self._timer_last_fire_lines[timer.id] = current_lines
            LOGGER.info(
                f"Timer '{timer.timer_name}' fired in #{channel_name} (announce={timer.announce})"
            )

        except Exception as e:
            LOGGER.error(f"Timer '{timer.timer_name}' fire failed: {e}")

    async def _fire_builtin_timer(
        self,
        channel_id: str,
        bt: BuiltinTimerDef,
        current_lines: int,
        now: datetime,
        bkey: tuple[str, str],
    ) -> None:
        """Send a builtin timer message and record the fire time/line snapshot."""
        try:
            channel_record = await self.bot.channels.get_channel(channel_id)
            channel_name = channel_record.channel_name if channel_record else None
            if not channel_name:
                LOGGER.warning(
                    f"Builtin timer '{bt.timer_name}': could not resolve channel name for {channel_id}"
                )
                return

            message = substitute_variables(bt.message_template, _NoChatter(), channel_name, "")

            users = await self.bot.fetch_users(ids=[channel_id])
            if not users:
                LOGGER.warning(
                    f"Builtin timer '{bt.timer_name}': could not fetch broadcaster for {channel_id}"
                )
                return

            sender_id = self.bot.sender_for(channel_id)
            if bt.announce:
                await users[0].send_announcement(
                    message=message,
                    moderator=sender_id,
                    color="primary",
                )
            else:
                await users[0].send_message(
                    message=message,
                    sender=sender_id,
                )

            self._builtin_last_fire[bkey] = now
            self._builtin_last_fire_lines[bkey] = current_lines
            LOGGER.info(
                f"Builtin timer '{bt.timer_name}' fired in #{channel_name} (announce={bt.announce})"
            )

        except Exception as e:
            LOGGER.error(f"Builtin timer '{bt.timer_name}' fire failed: {e}")


async def setup(bot: commands.Bot) -> None:
    component = TimerManagerComponent(bot)  # type: ignore[arg-type]
    await bot.add_component(component)


async def teardown(bot: commands.Bot) -> None: ...
