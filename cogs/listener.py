import asyncio
import discord
from discord.ext import commands
from utils.logger import BotLogger


class Listener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.handlers = []

        bot.loop.create_task(self.wait_and_register_handlers())

    async def wait_and_register_handlers(self):
        await self.bot.wait_until_ready()
        # 給其他 cogs 時間載入完成
        await asyncio.sleep(1)
        for cog in self.bot.cogs.values():
            if hasattr(cog, "handle_on_message") and cog != self:
                self.handlers.append(cog)
                BotLogger.info("Listener", f"註冊訊息處理器: {cog.__class__.__name__}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # 先處理自定義的 handle_on_message
        for handler in self.handlers:
            if handler:
                try:
                    await handler.handle_on_message(message)
                except Exception as e:
                    BotLogger.error("Listener", f"處理器 {handler.__class__.__name__} 錯誤", e)
        
        # 🔧 重要：確保 Discord.py 的指令處理機制正常運作
        await self.bot.process_commands(message)


async def setup(bot):
    listener = Listener(bot)
    await bot.add_cog(listener)
