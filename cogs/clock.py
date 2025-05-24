import asyncio
from datetime import datetime, timedelta

import discord
from discord.ext import commands


class Clock(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.clocked_in = {}  # user_id: datetime
        self.tasks = {}  # user_id: asyncio.Task

    @commands.command(name="cin", help="打卡，開始工作")
    async def clock_in(self, ctx: commands.Context):
        if ctx.guild is None:
            await ctx.send("❌ 此指令只能在伺服器中使用。")
            return

        uid = ctx.author.id
        now = datetime.now()

        if uid in self.clocked_in:
            await ctx.send(
                f"🕒 {ctx.author.mention} 你已經打過卡了（{self.clocked_in[uid].strftime('%Y-%m-%d %H:%M:%S')}）"
            )
            return

        self.clocked_in[uid] = now
        end_time = now + timedelta(hours=9)
        await ctx.send(
            f"✅ {ctx.author.mention} 成功打卡！\n🕑 打卡時間：**{now.strftime('%Y-%m-%d %H:%M:%S')}**\n⏰ 預計下班時間：**{end_time.strftime('%Y-%m-%d %H:%M:%S')}**"
        )

        # 啟動 countdown 任務
        task = asyncio.create_task(
            self.reminder_after_9_hours(ctx, uid, end_time))
        self.tasks[uid] = task

    async def reminder_after_9_hours(self, ctx: commands.Context, uid: int,
                                     end_time: datetime):
        try:
            await asyncio.sleep(9 * 3600)  # 9 小時
            if uid in self.clocked_in:  # 如果還沒下班
                member = ctx.guild.get_member(uid)
                if member:
                    await ctx.send(
                        f"🔔 {member.mention} 該下班囉！已經是 **{end_time.strftime('%Y-%m-%d %H:%M:%S')}** 啦！"
                    )
                self.clocked_in.pop(uid, None)
                self.tasks.pop(uid, None)
        except asyncio.CancelledError:
            pass  # 被提前下班取消就安靜結束

    @commands.command(name="cout", help="下班，結束工作")
    async def clock_out(self, ctx: commands.Context):
        if ctx.guild is None:
            await ctx.send("❌ 此指令只能在伺服器中使用。")
            return

        uid = ctx.author.id
        now = datetime.now()

        if uid not in self.clocked_in:
            await ctx.send(f"❌ {ctx.author.mention} 你還沒有打卡，無法下班。")
            return

        start_time = self.clocked_in.pop(uid)
        if uid in self.tasks:
            self.tasks[uid].cancel()
            self.tasks.pop(uid)

        worked_time = now - start_time
        hours, remainder = divmod(worked_time.total_seconds(), 3600)
        minutes, _ = divmod(remainder, 60)

        await ctx.send(
            f"👋 {ctx.author.mention} 下班成功！\n🕒 工作時長：**{int(hours)} 小時 {int(minutes)} 分鐘**"
        )

    @commands.command(name="attendance", help="查詢目前上班狀態")
    async def check_status(self, ctx: commands.Context):
        if ctx.guild is None:
            await ctx.send("❌ 此指令只能在伺服器中使用。")
            return

        uid = ctx.author.id
        if uid not in self.clocked_in:
            await ctx.send(f"📋 {ctx.author.mention} 你目前沒有打卡。")
        else:
            start_time = self.clocked_in[uid]
            now = datetime.now()
            elapsed = now - start_time
            hours, remainder = divmod(elapsed.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            await ctx.send(
                f"🕒 {ctx.author.mention} 你於 **{start_time.strftime('%Y-%m-%d %H:%M:%S')}** 打卡，目前已工作 **{int(hours)} 小時 {int(minutes)} 分鐘**。"
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Clock(bot))
