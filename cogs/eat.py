import discord
from discord.ext import commands


class Eat(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # 前綴指令
    @commands.command()
    async def eat(self, ctx: commands.Context):
        await ctx.send("要吃什麼?")


async def setup(bot: commands.Bot):
    await bot.add_cog(Eat(bot))
