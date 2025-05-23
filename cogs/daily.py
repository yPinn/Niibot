# todo：每日提示 (AM09:00)
# 內容：

# 可能可以新增 簽到 上班打卡
import discord
from discord.ext import commands


class Daily(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # 前綴指令
    @commands.command()
    async def x(self, ctx: commands.Context):
        await ctx.send("Hello, world!")


async def setup(bot: commands.Bot):
    await bot.add_cog(Daily(bot))
