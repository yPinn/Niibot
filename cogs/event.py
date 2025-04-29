import discord
from discord.ext import commands


class Event(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # 關鍵字觸發
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if message.author == self.bot.user:
            return
        if message.content.startswith("Hello"):
            await message.channel.send("Hello, world!")


async def setup(bot: commands.Bot):
    await bot.add_cog(Event(bot))
