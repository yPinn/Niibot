import asyncio
import discord
from discord.ext import commands
from utils.logger import BotLogger


class Listener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.handlers = []
        self._registered_handlers = set()  # 追蹤已註冊的處理器，避免重複

        bot.loop.create_task(self.wait_and_register_handlers())

    async def wait_and_register_handlers(self):
        await self.bot.wait_until_ready()
        # 給其他 cogs 時間載入完成
        await asyncio.sleep(1)
        
        # 清空現有處理器列表，重新註冊（避免重載時重複）
        self.handlers.clear()
        self._registered_handlers.clear()
        
        for cog in self.bot.cogs.values():
            if hasattr(cog, "handle_on_message") and cog != self:
                # 使用 cog 的記憶體位址作為唯一識別符，避免重複註冊
                cog_id = id(cog)
                if cog_id not in self._registered_handlers:
                    self.handlers.append(cog)
                    self._registered_handlers.add(cog_id)
                    BotLogger.info("Listener", f"註冊訊息處理器: {cog.__class__.__name__}")
                else:
                    BotLogger.debug("Listener", f"跳過重複註冊: {cog.__class__.__name__}")

    def cog_unload(self):
        """Cog 卸載時清理處理器"""
        BotLogger.info("Listener", "清理訊息處理器...")
        self.handlers.clear()
        self._registered_handlers.clear()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # 先處理自定義的 handle_on_message
        # 使用 copy() 避免在迭代過程中列表被修改
        for handler in self.handlers.copy():
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
