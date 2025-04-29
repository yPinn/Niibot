import discord
from discord.ext import commands


class Eat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # 前綴指令
    @commands.command()
    async def eat(self, ctx: commands.Context):
        await ctx.send("要吃什麼?")

    # 關鍵字觸發
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return
        if message.content.startswith("Hello"):
            await message.channel.send("Hello, world!")


async def setup(bot: commands.Bot):
    await bot.add_cog(Eat(bot))
