from datetime import UTC
from typing import TYPE_CHECKING

import twitchio
from twitchio.ext import commands

from core.bot import _substitute_variables
from core.config import get_settings
from core.guards import check_command
from shared.repositories.command_config import CommandConfigRepository

FRONTEND_URL = get_settings().frontend_url.rstrip("/")

if TYPE_CHECKING:
    from core.bot import Bot


class GeneralCommands(commands.Component):
    """General user commands for the bot."""

    COMMANDS: list[dict] = [
        {"command_name": "hi", "custom_response": "你好,$(user)!", "cooldown": 5},
        {"command_name": "help", "cooldown": 5},
        {"command_name": "uptime", "cooldown": 5},
        {"command_name": "斥責", "cooldown": 10, "aliases": "嚴厲斥責"},
    ]

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self.cmd_repo = CommandConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.channel_repo = self.bot.channels  # type: ignore[attr-defined]

    async def _record_command(self, ctx: commands.Context, command_name: str) -> None:
        """Helper to record command usage to analytics"""
        try:
            channel_id = ctx.channel.id
            if hasattr(self.bot, "_active_sessions") and hasattr(self.bot, "analytics"):
                session_id = self.bot._active_sessions.get(channel_id)
                if session_id:
                    analytics = self.bot.analytics
                    await analytics.record_command_usage(
                        session_id=session_id,
                        channel_id=channel_id,
                        command_name=f"!{command_name}",
                    )
        except Exception as e:
            from core.bot import LOGGER

            LOGGER.error(f"Failed to record command usage: {e}")

    @commands.command(aliases=["hello", "hey"])
    async def hi(self, ctx: commands.Context) -> None:
        """Greet the user.

        Usage: !hi, !hello, !hey
        """
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="hi"
        )
        if not config:
            return

        # Use custom response if set, otherwise default
        if config.custom_response:
            response = _substitute_variables(
                config.custom_response, ctx.chatter, ctx.channel.name, ""
            )
            await ctx.reply(response)
        else:
            await ctx.reply(f"你好，{ctx.chatter.display_name}！")
        await self._record_command(ctx, "hi")

    @commands.command(aliases=["commands"])
    async def help(self, ctx: commands.Context) -> None:
        """Show available commands.

        Usage: !help, !commands
        """
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="help"
        )
        if not config:
            return

        channel_name = ctx.channel.name
        await ctx.reply(f"此頻道的指令列表： {FRONTEND_URL}/{channel_name}/commands")
        await self._record_command(ctx, "help")

    @commands.command()
    async def uptime(self, ctx: commands.Context) -> None:
        """Show stream uptime.

        Usage: !uptime
        """
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="uptime"
        )
        if not config:
            return

        streams = await ctx.bot.fetch_streams(user_ids=[ctx.channel.id])

        if streams:
            stream = streams[0]
            if stream.started_at:
                from datetime import datetime

                now = datetime.now(UTC)
                uptime = now - stream.started_at
                hours, remainder = divmod(int(uptime.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                await ctx.reply(f"已開播 {hours} 小時 {minutes} 分 {seconds} 秒")
            else:
                await ctx.reply("目前未開播")
        else:
            await ctx.reply("目前未開播")

        await self._record_command(ctx, "uptime")

    @commands.command(name="斥責", aliases=["嚴厲斥責"])
    async def condemn(self, ctx: commands.Context) -> None:
        """頻道反惡意言論聲明。

        Usage: !斥責
        """
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="斥責"
        )
        if not config:
            return

        await ctx.send(
            "本頻道實況主不認可並嚴厲斥責聊天室與斗內的任何惡意言論，"
            "包含且不限於種族歧視、性騷擾、色情暴力、涉及親屬等不當內容。"
        )
        await self._record_command(ctx, "斥責")

    @commands.Component.listener()
    async def event_stream_online(self, payload: twitchio.StreamOnline) -> None:
        from datetime import datetime

        from core.bot import LOGGER

        LOGGER.info(f"頻道 {payload.broadcaster.name} 開始直播！")

        try:
            if not (hasattr(self.bot, "_active_sessions") and hasattr(self.bot, "analytics")):
                return

            channel_id = payload.broadcaster.id
            active_sessions = self.bot._active_sessions

            existing_session = active_sessions.get(channel_id)
            if existing_session:
                LOGGER.warning(
                    f"Channel {payload.broadcaster.name} already has active session {existing_session}, skipping"
                )
                return

            streams = await self.bot.fetch_streams(user_ids=[channel_id])
            title = streams[0].title if streams else None
            game_name = streams[0].game_name if streams else None
            game_id = str(streams[0].game_id) if streams and streams[0].game_id else None

            analytics = self.bot.analytics
            session_id = await analytics.create_session(
                channel_id=channel_id,
                started_at=datetime.now(),
                title=title,
                game_name=game_name,
                game_id=game_id,
            )
            active_sessions[channel_id] = session_id
            LOGGER.info(
                f"Created analytics session {session_id} for channel {payload.broadcaster.name}"
            )
        except Exception as e:
            LOGGER.error(f"Failed to create analytics session: {e}")

    @commands.Component.listener()
    async def event_stream_offline(self, payload: twitchio.StreamOffline) -> None:
        import asyncio
        from datetime import datetime

        from core.bot import LOGGER

        LOGGER.info(f"頻道 {payload.broadcaster.name} 結束直播")

        try:
            if not (hasattr(self.bot, "_active_sessions") and hasattr(self.bot, "analytics")):
                return

            channel_id = payload.broadcaster.id
            active_sessions = self.bot._active_sessions
            session_id = active_sessions.get(channel_id)

            if session_id:
                analytics = self.bot.analytics

                # Flush chatter stats buffer to database
                if hasattr(self.bot, "_chatter_buffers"):
                    chatter_data = self.bot._chatter_buffers.pop(channel_id, {})
                    if chatter_data:
                        try:
                            await analytics.flush_chatter_stats(
                                session_id=session_id,
                                channel_id=channel_id,
                                chatters=chatter_data,
                            )
                            LOGGER.info(
                                f"Flushed {len(chatter_data)} chatters for session {session_id}"
                            )
                        except Exception as e:
                            LOGGER.error(f"Failed to flush chatter stats: {e}")

                ended_at = datetime.now()
                for attempt in range(3):
                    try:
                        await analytics.end_session(session_id, ended_at)
                        break
                    except Exception as e:
                        LOGGER.warning(f"end_session attempt {attempt + 1}/3 failed: {e}")
                        if attempt < 2:
                            await asyncio.sleep(2)
                else:
                    LOGGER.error(
                        f"Failed to end session {session_id} after 3 attempts, "
                        "stale session cleanup will handle it"
                    )
                del active_sessions[channel_id]
                LOGGER.info(
                    f"Ended analytics session {session_id} for channel {payload.broadcaster.name}"
                )
            else:
                LOGGER.warning(f"No active session found for channel {payload.broadcaster.name}")
        except Exception as e:
            LOGGER.error(f"Failed to end analytics session: {e}")


async def setup(bot: commands.Bot) -> None:
    """Entry point for the module."""
    await bot.add_component(GeneralCommands(bot))


async def teardown(bot: commands.Bot) -> None:
    """Optional teardown coroutine for cleanup."""
    ...
