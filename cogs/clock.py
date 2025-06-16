import asyncio
import os
from datetime import datetime, timedelta

import discord
from discord.ext import commands
from discord.utils import get

from utils.util import read_json, write_json, now_local, format_datetime

DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "clock.json")
WORK_HOURS = 9


def guild_only_check():
    async def predicate(ctx):
        if ctx.guild is None:
            await ctx.send("❌ 此指令只能在伺服器中使用。")
            return False
        return True
    return commands.check(predicate)


class Clock(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.clocked_in = {}  # user_id -> {"time": datetime, "channel_id": int}
        self.reminded_10min = set()
        self.loop_task = None

    async def initialize(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.exists(DATA_FILE) or os.stat(DATA_FILE).st_size == 0:
            await write_json(DATA_FILE, {})
            self.clocked_in = {}
            return

        raw_data = await read_json(DATA_FILE) or {}
        self.clocked_in = {
            int(uid): {
                "time": datetime.fromisoformat(info["time"]),
                "channel_id": info["channel_id"]
            }
            for uid, info in raw_data.items()
        }

    async def save_clock_data(self):
        to_save = {
            str(uid): {
                "time": info["time"].isoformat(),
                "channel_id": info["channel_id"]
            }
            for uid, info in self.clocked_in.items()
        }
        await write_json(DATA_FILE, to_save)

    @commands.Cog.listener()
    async def on_ready(self):
        if self.loop_task is None:
            await self.initialize()
            print("[Clock] 打卡資料載入完成。")
            self.loop_task = self.bot.loop.create_task(self.check_clock_loop())

    async def check_clock_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                now = now_local()
                to_remove = []

                for uid, info in list(self.clocked_in.items()):
                    start_time = info["time"]
                    end_time = start_time + timedelta(hours=WORK_HOURS)
                    channel = self.bot.get_channel(info["channel_id"])
                    if channel is None:
                        continue
                    member = get(channel.guild.members, id=uid)
                    if member is None:
                        continue

                    time_left = (end_time - now).total_seconds()

                    if 0 < time_left <= 600 and uid not in self.reminded_10min:
                        await channel.send(f"⌛ {member.mention} 還有 10 分鐘就下班囉！")
                        self.reminded_10min.add(uid)

                    elif time_left <= 0:
                        await channel.send(
                            f"🔔 {member.mention} 該下班囉！\n已經是 **{format_datetime(now)}** 啦！"
                        )
                        to_remove.append(uid)

                for uid in to_remove:
                    self.clocked_in.pop(uid, None)
                    self.reminded_10min.discard(uid)

                if to_remove:
                    await self.save_clock_data()

                await asyncio.sleep(60)
            except Exception as e:
                print(f"[Clock] check_clock_loop 發生錯誤: {e}")
                await asyncio.sleep(60)

    @commands.command(name="cin", help="上班打卡")
    @guild_only_check()
    async def clock_in(self, ctx: commands.Context):
        uid = ctx.author.id
        now = now_local()

        if uid in self.clocked_in:
            old_time = self.clocked_in[uid]["time"]
            await ctx.send(
                f"🕒 {ctx.author.mention} 你已經打過卡了（{format_datetime(old_time)}）"
            )
            return

        self.clocked_in[uid] = {"time": now, "channel_id": ctx.channel.id}
        await self.save_clock_data()

        end_time = now + timedelta(hours=WORK_HOURS)

        embed = discord.Embed(
            title="✅ 打卡成功！",
            color=discord.Color.green(),
            timestamp=now
        )
        embed.set_author(name=ctx.author.display_name,
                         icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        embed.add_field(
            name="🕑 打卡時間", value=format_datetime(now), inline=False)
        embed.add_field(name="⏰ 預計下班時間", value=format_datetime(
            end_time), inline=False)
        embed.set_footer(text=f"工作時間為 {WORK_HOURS} 小時")

        await ctx.send(embed=embed)

    @commands.command(name="cout", help="下班打卡")
    @guild_only_check()
    async def clock_out(self, ctx: commands.Context):
        uid = ctx.author.id
        now = now_local()

        if uid not in self.clocked_in:
            await ctx.send(f"❌ {ctx.author.mention} 你還沒有打卡，無法下班。")
            return

        start_time = self.clocked_in.pop(uid)["time"]
        self.reminded_10min.discard(uid)
        await self.save_clock_data()

        worked_time = now - start_time
        hours, remainder = divmod(worked_time.total_seconds(), 3600)
        minutes, _ = divmod(remainder, 60)

        await ctx.send(
            f"👋 {ctx.author.mention} 下班成功！\n"
            f"🕒 工作時長：**{int(hours)} 小時 {int(minutes)} 分鐘**"
        )

    @commands.command(name="wS", help="查詢目前上班狀態")
    @guild_only_check()
    async def check_status(self, ctx: commands.Context):
        uid = ctx.author.id
        if uid not in self.clocked_in:
            await ctx.send(f"📋 {ctx.author.mention} 你目前沒有打卡。")
        else:
            start_time = self.clocked_in[uid]["time"]
            now = now_local()
            elapsed = now - start_time
            hours, remainder = divmod(elapsed.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            await ctx.send(
                f"🕒 {ctx.author.mention} \n你於 **{format_datetime(start_time)}** 打卡，\n"
                f"目前已工作 **{int(hours)} 小時 {int(minutes)} 分鐘**。"
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Clock(bot))
