import asyncio
import discord
from discord.ext import commands
from utils.logger import BotLogger


class Listener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.handlers = []
        self._registered_handlers = set()  # 追蹤已註冊的處理器，避免重複
        self._registered_cog_names = set()  # 使用類別名稱去重，避免記憶體位址重用問題

        bot.loop.create_task(self.wait_and_register_handlers())

    async def wait_and_register_handlers(self):
        await self.bot.wait_until_ready()
        # 給其他 cogs 時間載入完成
        await asyncio.sleep(1)
        
        # 清空現有處理器列表，重新註冊（避免重載時重複）
        self.handlers.clear()
        self._registered_handlers.clear()
        self._registered_cog_names.clear()
        
        BotLogger.info("Listener", "開始註冊訊息處理器...")
        
        for cog in self.bot.cogs.values():
            if hasattr(cog, "handle_on_message") and cog != self:
                # 使用類別名稱和記憶體位址雙重檢查，確保絕對不重複
                cog_name = cog.__class__.__name__
                cog_id = id(cog)
                
                if cog_name not in self._registered_cog_names and cog_id not in self._registered_handlers:
                    self.handlers.append(cog)
                    self._registered_handlers.add(cog_id)
                    self._registered_cog_names.add(cog_name)
                    BotLogger.info("Listener", f"註冊訊息處理器: {cog_name} (ID: {hex(cog_id)})")
                else:
                    BotLogger.warning("Listener", f"跳過重複註冊: {cog_name} (已存在: 名稱={cog_name in self._registered_cog_names}, ID={cog_id in self._registered_handlers})")
        
        BotLogger.info("Listener", f"訊息處理器註冊完成，共註冊 {len(self.handlers)} 個處理器")

    def cog_unload(self):
        """Cog 卸載時清理處理器"""
        BotLogger.info("Listener", "清理訊息處理器...")
        self.handlers.clear()
        self._registered_handlers.clear()
        self._registered_cog_names.clear()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # 防止同時處理同一訊息的簡單鎖機制
        message_id = message.id
        processing_key = f"processing_{message_id}"
        
        # 檢查是否已經在處理此訊息
        if hasattr(self, processing_key):
            BotLogger.debug("Listener", f"訊息 {message_id} 已在處理中，跳過重複處理")
            return
        
        # 標記正在處理
        setattr(self, processing_key, True)
        
        try:
            # 先處理自定義的 handle_on_message
            # 使用 copy() 避免在迭代過程中列表被修改
            for handler in self.handlers.copy():
                if handler:
                    try:
                        BotLogger.debug("Listener", f"調用處理器: {handler.__class__.__name__}")
                        await handler.handle_on_message(message)
                    except Exception as e:
                        BotLogger.error("Listener", f"處理器 {handler.__class__.__name__} 錯誤", e)
            
            # 🔧 重要：確保 Discord.py 的指令處理機制正常運作
            await self.bot.process_commands(message)
            
        finally:
            # 清理處理標記
            if hasattr(self, processing_key):
                delattr(self, processing_key)

    @commands.command(name="debug_handlers", help="顯示當前註冊的訊息處理器狀態")
    async def debug_handlers(self, ctx):
        """除錯指令：顯示當前處理器註冊狀態"""
        import discord
        
        embed = discord.Embed(
            title="🔍 訊息處理器除錯資訊",
            color=discord.Color.blue()
        )
        
        # 基本統計
        embed.add_field(
            name="📊 基本統計",
            value=f"註冊處理器數量: {len(self.handlers)}\n"
                  f"記憶體位址追蹤: {len(self._registered_handlers)}\n"
                  f"類別名稱追蹤: {len(self._registered_cog_names)}",
            inline=False
        )
        
        # 處理器詳情
        if self.handlers:
            handler_info = []
            for i, handler in enumerate(self.handlers, 1):
                handler_info.append(f"{i}. {handler.__class__.__name__} (ID: {hex(id(handler))})")
            
            embed.add_field(
                name="🎯 已註冊處理器",
                value="\n".join(handler_info[:10]) + ("\n..." if len(handler_info) > 10 else ""),
                inline=False
            )
        else:
            embed.add_field(
                name="⚠️ 狀態",
                value="沒有註冊任何處理器",
                inline=False
            )
        
        # 檢查是否有重複
        cog_names = [h.__class__.__name__ for h in self.handlers]
        duplicates = [name for name in set(cog_names) if cog_names.count(name) > 1]
        
        if duplicates:
            embed.add_field(
                name="🚨 發現重複",
                value=f"重複的處理器: {', '.join(duplicates)}",
                inline=False
            )
        
        await ctx.send(embed=embed)
        BotLogger.command_used("debug_handlers", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"處理器數量: {len(self.handlers)}")


async def setup(bot):
    listener = Listener(bot)
    await bot.add_cog(listener)
