import twitchio
from twitchio.ext import commands
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import Bot
else:
    from twitchio.ext.commands import Bot


class GeneralCommands(commands.Component):
    """General user commands for the bot."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(aliases=["hello", "hey"])
    async def hi(self, ctx: commands.Context[Bot]) -> None:
        """Greet the user.

        Usage: !hi, !hello, !hey
        """
        await ctx.reply(f"你好，{ctx.chatter.display_name}！")

    @commands.command(aliases=["commands"])
    async def help(self, ctx: commands.Context[Bot]) -> None:
        """Show available commands.

        Usage: !help, !commands
        """
        await ctx.reply("可用指令：!hi, !uptime, !ai <問題>, !運勢, !rk [玩家ID], !redemptions")

    @commands.command()
    async def uptime(self, ctx: commands.Context[Bot]) -> None:
        """Show stream uptime.

        Usage: !uptime
        """
        # ctx.channel 是 PartialUser，直接使用 .id 屬性
        # 在 TwitchIO 3 中，PartialUser.id 就是 broadcaster_user_id
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

    @commands.Component.listener()
    async def event_stream_online(self, payload: twitchio.StreamOnline) -> None:
        """Log when a subscribed channel goes live."""
        from main import LOGGER

        LOGGER.info(f"頻道 {payload.broadcaster.name} 開始直播！")


async def setup(bot: commands.Bot) -> None:
    """Entry point for the module."""
    await bot.add_component(GeneralCommands(bot))


async def teardown(bot: commands.Bot) -> None:
    """Optional teardown coroutine for cleanup."""
    ...
