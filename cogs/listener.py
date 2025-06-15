import asyncio
import discord
from discord.ext import commands
from utils.logger import BotLogger


class Listener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.handlers = []
        self._registration_task = None
        
        # 簡單的實例ID用於除錯
        self._instance_id = id(self)
        BotLogger.info("Listener", f"🔧 建立Listener實例 {hex(self._instance_id)}")
        
        self._start_registration_task()
    
    def _start_registration_task(self):
        """啟動註冊任務"""
        self._registration_task = self.bot.loop.create_task(self.wait_and_register_handlers())

    async def wait_and_register_handlers(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(1)  # 等待其他cog載入
        
        self.handlers.clear()  # 清空重新註冊
        BotLogger.info("Listener", "🔍 掃描有handle_on_message的cog...")
        
        for cog in self.bot.cogs.values():
            if hasattr(cog, "handle_on_message") and cog != self:
                cog_name = cog.__class__.__name__
                self.handlers.append(cog)
                BotLogger.info("Listener", f"✅ 註冊處理器: {cog_name}")
        
        BotLogger.info("Listener", f"📋 註冊完成，共 {len(self.handlers)} 個處理器")

    def cog_unload(self):
        """Cog 卸載時清理"""
        BotLogger.info("Listener", f"🗑️ 清理實例 {hex(self._instance_id)}")
        if self._registration_task and not self._registration_task.done():
            self._registration_task.cancel()
        self.handlers.clear()

    # @commands.Cog.listener()
    async def on_message_disabled(self, message: discord.Message):
        if message.author.bot:
            return
        
        # 檢查是否有多個listener實例在處理同一訊息
        BotLogger.info("Listener", f"🔍 Cog實例列表: {list(self.bot.cogs.keys())}")
        listener_cogs = [name for name in self.bot.cogs.keys() if 'listener' in name.lower()]
        BotLogger.info("Listener", f"🔍 Listener相關Cog: {listener_cogs}")
        
        # 最基本的日誌記錄
        BotLogger.info("Listener", f"📨 實例{hex(self._instance_id)} 收到: {message.content[:30]}...")
        
        try:
            # 暫時禁用handler，專注測試process_commands
            # for handler in self.handlers:
            #     try:
            #         await handler.handle_on_message(message)
            #     except Exception as e:
            #         BotLogger.error("Listener", f"處理器錯誤: {e}")
            
            # 處理Discord指令
            BotLogger.info("Listener", f"🚀 實例{hex(self._instance_id)} 處理指令: {message.content[:30]}...")
            await self.bot.process_commands(message)
            
        except Exception as e:
            BotLogger.error("Listener", f"on_message錯誤: {e}")

    @commands.command(name="debug_commands", help="顯示當前註冊的指令")
    async def debug_commands(self, ctx):
        """除錯指令：顯示所有註冊的指令"""
        import discord
        
        embed = discord.Embed(
            title="🔍 指令註冊診斷",
            color=discord.Color.blue()
        )
        
        # 檢查所有註冊的指令
        commands_list = []
        for name, command in self.bot.all_commands.items():
            commands_list.append(f"• {name}: {command.callback.__name__} (在 {command.callback.__module__})")
        
        embed.add_field(
            name="📋 已註冊指令",
            value="\n".join(commands_list[:10]) + ("\n..." if len(commands_list) > 10 else ""),
            inline=False
        )
        
        # 特別檢查test指令
        test_command = self.bot.get_command("test")
        if test_command:
            embed.add_field(
                name="🧪 test指令詳情",
                value=f"回調: {test_command.callback}\n模組: {test_command.callback.__module__}",
                inline=False
            )
        
        await ctx.send(embed=embed)

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
