import discord
from discord.ext import commands
import json
import os

DATA_FILE = 'data/tinder.json'


class Tinder(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.user_data = self.load_data()

    def load_data(self):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                return json.load(f)

        return {}

    def save_data(self):
        with open(DATA_FILE, "w") as f:
            json.dump(self.user_data, f, indent=4)

    @commands.command()
    async def status(self, ctx: commands.Context):
        uid = str(ctx.author.id)
        if uid in self.user_data:
            data = self.user_data[uid]
            await ctx.send()

    # 前綴指令

    @commands.command()
    async def tinder(self, ctx: commands.Context):
        await ctx.send("MATCH!!!")

    # 關鍵字觸發
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return
        if message.content.startswith("Hello"):
            await message.channel.send("Hello, world!")


async def setup(bot: commands.Bot):
    await bot.add_cog(Tinder(bot))
