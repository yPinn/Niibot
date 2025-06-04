import discord
from discord.ext import commands


class Listener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.handlers = []

        bot.loop.create_task(self.wait_and_register_handlers())

    async def wait_and_register_handlers(self):
        await self.bot.wait_until_ready()
        for cog in self.bot.cogs.values():
            if hasattr(cog, "handle_on_message") and cog != self:
                self.handlers.append(cog)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        for handler in self.handlers:
            if handler:
                try:
                    await handler.handle_on_message(message)
                except Exception as e:
                    print(f"Error in handle_on_message of {handler}: {e}")


async def setup(bot):
    listener = Listener(bot)
    await bot.add_cog(listener)
