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
        self._registration_task = None  # 追蹤註冊任務，避免重複執行
        self._processing_messages = set()  # 追蹤正在處理的訊息ID，避免重複處理
        self._recent_messages = {}  # 追蹤最近處理的訊息，防止重複
        
        # 記錄listener實例，用於除錯
        self._instance_id = id(self)
        BotLogger.info("Listener", f"建立新的Listener實例 (ID: {hex(self._instance_id)})")
        
        self._start_registration_task()
    
    def _start_registration_task(self):
        """啟動註冊任務，確保不會重複執行"""
        if self._registration_task is None or self._registration_task.done():
            self._registration_task = self.bot.loop.create_task(self.wait_and_register_handlers())
            BotLogger.debug("Listener", "啟動新的處理器註冊任務")
        else:
            BotLogger.warning("Listener", "註冊任務已在執行中，跳過重複啟動")

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
        
        # 取消註冊任務
        if self._registration_task and not self._registration_task.done():
            self._registration_task.cancel()
            BotLogger.debug("Listener", "取消註冊任務")
        
        # 清理處理器
        self.handlers.clear()
        self._registered_handlers.clear()
        self._registered_cog_names.clear()
        self._processing_messages.clear()
        
        # 清理重複訊息快取
        if hasattr(self, '_recent_messages'):
            self._recent_messages.clear()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        
        # 忽略編輯過的訊息，避免重複觸發
        if message.edited_at is not None:
            BotLogger.debug("Listener", f"忽略編輯訊息 {message.id}")
            return
        
        # 確保只有主要的listener實例處理訊息
        BotLogger.debug("Listener", f"Listener實例 {hex(self._instance_id)} 接收到訊息: {message.content[:30]}...")

        # 強化的防重複機制：使用訊息內容哈希和時間戳
        message_id = message.id
        message_hash = hash((message.content, message.author.id, message.channel.id))
        current_time = asyncio.get_event_loop().time()
        
        # 檢查是否已經在處理此訊息
        if message_id in self._processing_messages:
            BotLogger.warning("Listener", f"⚠️ 訊息 {message_id} 已在處理中，跳過重複處理 - 內容: {message.content[:30]}...")
            return
        
        # 防止短時間內重複處理相同內容的訊息（Discord重傳問題）
        if hasattr(self, '_recent_messages'):
            recent_threshold = current_time - 3.0  # 增加到3秒內的重複訊息
            self._recent_messages = {k: v for k, v in self._recent_messages.items() if v > recent_threshold}
            
            if message_hash in self._recent_messages:
                time_diff = current_time - self._recent_messages[message_hash]
                BotLogger.warning("Listener", f"🔄 偵測到重複訊息內容，跳過處理 - 內容: {message.content[:30]}... (間隔: {time_diff:.2f}s)")
                return
        else:
            self._recent_messages = {}
        
        # 標記正在處理和記錄訊息
        self._processing_messages.add(message_id)
        self._recent_messages[message_hash] = current_time
        
        # 記錄開始處理
        BotLogger.debug("Listener", f"🚀 開始處理訊息 {message_id}: {message.content[:30]}...")
        
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
            BotLogger.debug("Listener", f"處理指令: {message.content[:50]}...")
            await self.bot.process_commands(message)
            
        finally:
            # 清理處理標記
            self._processing_messages.discard(message_id)
            
            # 定期清理舊的訊息ID，避免記憶體洩漏
            if len(self._processing_messages) > 1000:
                BotLogger.warning("Listener", f"處理訊息集合過大 ({len(self._processing_messages)})，清理中...")
                self._processing_messages.clear()

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
    
    @commands.command(name="debug_listeners", help="檢查所有 cog 的 on_message 監聽器")
    async def debug_listeners(self, ctx):
        """全面檢查所有可能的 on_message 重複監聽問題"""
        import discord
        
        embed = discord.Embed(
            title="🚨 on_message 監聽器診斷",
            description="檢查所有可能導致重複回復的監聽器",
            color=discord.Color.red()
        )
        
        # 檢查所有 cogs 的 listener 裝飾器
        direct_listeners = []
        handle_on_message_cogs = []
        
        for cog_name, cog in self.bot.cogs.items():
            # 檢查是否有直接的 @commands.Cog.listener() on_message
            if hasattr(cog, '__cog_listeners__'):
                listeners = getattr(cog, '__cog_listeners__', {})
                if 'on_message' in listeners:
                    direct_listeners.append(f"{cog_name} (有直接監聽器)")
            
            # 檢查是否有 handle_on_message 方法
            if hasattr(cog, 'handle_on_message'):
                handle_on_message_cogs.append(f"{cog_name} (有 handle_on_message)")
        
        # 顯示直接監聽器
        if direct_listeners:
            embed.add_field(
                name="⚠️ 直接 on_message 監聽器",
                value="\n".join(direct_listeners),
                inline=False
            )
        else:
            embed.add_field(
                name="✅ 直接 on_message 監聽器",
                value="沒有發現額外的直接監聽器",
                inline=False
            )
        
        # 顯示 handle_on_message 方法
        if handle_on_message_cogs:
            embed.add_field(
                name="📋 handle_on_message 方法",
                value="\n".join(handle_on_message_cogs),
                inline=False
            )
        
        # 檢查潛在的重複問題
        potential_issues = []
        if len(direct_listeners) > 1:
            potential_issues.append("發現多個直接 on_message 監聽器！")
        
        if len(self.handlers) != len(handle_on_message_cogs) - 1:  # -1 因為 listener 自己也算
            potential_issues.append(f"註冊的處理器數量({len(self.handlers)}) 與 handle_on_message 方法數量不符")
        
        if potential_issues:
            embed.add_field(
                name="🚨 潛在問題",
                value="\n".join(potential_issues),
                inline=False
            )
        else:
            embed.add_field(
                name="✅ 狀態",
                value="沒有發現明顯的重複監聽問題",
                inline=False
            )
        
        await ctx.send(embed=embed)
        BotLogger.command_used("debug_listeners", ctx.author.id, ctx.guild.id if ctx.guild else 0, 
                             f"直接監聽器: {len(direct_listeners)}, handle方法: {len(handle_on_message_cogs)}")


async def setup(bot):
    listener = Listener(bot)
    await bot.add_cog(listener)
