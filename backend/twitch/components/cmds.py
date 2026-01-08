from typing import TYPE_CHECKING

import twitchio
from twitchio.ext import commands

if TYPE_CHECKING:
    pass
else:
    pass


class GeneralCommands(commands.Component):
    """General user commands for the bot."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _record_command(self, ctx: commands.Context, command_name: str) -> None:
        """Helper to record command usage to analytics"""
        try:
            channel_id = ctx.channel.id
            if hasattr(self.bot, '_active_sessions') and hasattr(self.bot, 'analytics'):
                session_id = getattr(self.bot, '_active_sessions').get(channel_id)
                if session_id:
                    analytics = getattr(self.bot, 'analytics')
                    await analytics.record_command_usage(
                        session_id=session_id,
                        channel_id=channel_id,
                        command_name=f"!{command_name}"
                    )
        except Exception as e:
            from main import LOGGER
            LOGGER.error(f"Failed to record command usage: {e}")

    @commands.command(aliases=["hello", "hey"])
    async def hi(self, ctx: commands.Context) -> None:
        """Greet the user.

        Usage: !hi, !hello, !hey
        """
        await ctx.reply(f"你好，{ctx.chatter.display_name}！")
        await self._record_command(ctx, "hi")

    @commands.command(aliases=["commands"])
    async def help(self, ctx: commands.Context) -> None:
        """Show available commands.

        Usage: !help, !commands
        """
        await ctx.reply("可用指令：!hi, !uptime, !ai <問題>, !運勢, !rk [玩家ID], !redemptions")
        await self._record_command(ctx, "help")

    @commands.command()
    async def uptime(self, ctx: commands.Context) -> None:
        """Show stream uptime.

        Usage: !uptime
        """
        streams = await ctx.bot.fetch_streams(user_ids=[ctx.channel.id])

        if streams:
            stream = streams[0]
            if stream.started_at:
                from datetime import datetime, timezone

                now = datetime.now(timezone.utc)
                uptime = now - stream.started_at
                hours, remainder = divmod(int(uptime.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                await ctx.reply(f"已開播 {hours} 小時 {minutes} 分 {seconds} 秒")
            else:
                await ctx.reply("目前未開播")
        else:
            await ctx.reply("目前未開播")

        await self._record_command(ctx, "uptime")

    @commands.Component.listener()
    async def event_stream_online(self, payload: twitchio.StreamOnline) -> None:
        from datetime import datetime

        from main import LOGGER

        LOGGER.info(f"頻道 {payload.broadcaster.name} 開始直播！")

        try:
            if not (hasattr(self.bot, '_active_sessions') and hasattr(self.bot, 'analytics')):
                return

            channel_id = payload.broadcaster.id
            active_sessions = getattr(self.bot, '_active_sessions')

            existing_session = active_sessions.get(channel_id)
            if existing_session:
                LOGGER.warning(f"Channel {payload.broadcaster.name} already has active session {existing_session}, skipping")
                return

            streams = await self.bot.fetch_streams(user_ids=[channel_id])
            title = streams[0].title if streams else None
            game_name = streams[0].game_name if streams else None

            analytics = getattr(self.bot, 'analytics')
            session_id = await analytics.create_session(
                channel_id=channel_id,
                started_at=datetime.now(),
                title=title,
                game_name=game_name
            )
            active_sessions[channel_id] = session_id
            LOGGER.info(f"Created analytics session {session_id} for channel {payload.broadcaster.name}")
        except Exception as e:
            LOGGER.error(f"Failed to create analytics session: {e}")

    @commands.Component.listener()
    async def event_stream_offline(self, payload: twitchio.StreamOffline) -> None:
        from datetime import datetime

        from main import LOGGER

        LOGGER.info(f"頻道 {payload.broadcaster.name} 結束直播")

        try:
            if not (hasattr(self.bot, '_active_sessions') and hasattr(self.bot, 'analytics')):
                return

            channel_id = payload.broadcaster.id
            active_sessions = getattr(self.bot, '_active_sessions')
            session_id = active_sessions.get(channel_id)

            if session_id:
                analytics = getattr(self.bot, 'analytics')
                await analytics.end_session(session_id, datetime.now())
                del active_sessions[channel_id]
                LOGGER.info(f"Ended analytics session {session_id} for channel {payload.broadcaster.name}")
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
