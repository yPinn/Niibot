import asyncio
import discord
from discord.ext import commands
from utils.logger import BotLogger


class HandlerInfo:
    """處理器資訊類別"""
    def __init__(self, handler, priority=0, name=None):
        self.handler = handler
        self.priority = priority  # 數字越大優先級越高
        self.name = name or handler.__class__.__name__
        self.error_count = 0
        self.last_error = None
        self.disabled = False


class Listener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.handlers = []  # List[HandlerInfo]
        self._registration_task = None
        
        # 簡單的實例ID用於除錯
        self._instance_id = id(self)
        BotLogger.info("Listener", f"🔧 建立Listener實例 {hex(self._instance_id)}")
        
        # 處理器管理設定
        self.max_errors_per_handler = 5  # 每個處理器最大錯誤次數
        self.error_reset_threshold = 100  # 處理多少訊息後重置錯誤計數
        self.message_count = 0
        
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
                
                # 取得處理器優先級（如果有定義的話）
                priority = getattr(cog, 'message_handler_priority', 0)
                
                handler_info = HandlerInfo(cog, priority, cog_name)
                self.handlers.append(handler_info)
                BotLogger.info("Listener", f"✅ 註冊處理器: {cog_name} (優先級: {priority})")
        
        # 按優先級排序（高優先級先執行）
        self.handlers.sort(key=lambda h: h.priority, reverse=True)
        
        BotLogger.info("Listener", f"📋 註冊完成，共 {len(self.handlers)} 個處理器")
        for handler_info in self.handlers:
            BotLogger.debug("Listener", f"處理器順序: {handler_info.name} (優先級: {handler_info.priority})")

    async def handle_message_dispatch(self, message: discord.Message):
        """改進的訊息分發機制"""
        self.message_count += 1
        
        # 定期重置錯誤計數
        if self.message_count % self.error_reset_threshold == 0:
            for handler_info in self.handlers:
                if handler_info.error_count > 0:
                    BotLogger.info("Listener", f"重置 {handler_info.name} 的錯誤計數: {handler_info.error_count} -> 0")
                    handler_info.error_count = 0
                    handler_info.disabled = False
        
        # 按優先級順序處理
        for handler_info in self.handlers:
            if handler_info.disabled:
                continue
                
            try:
                # 檢查處理器是否有條件處理方法
                if hasattr(handler_info.handler, 'should_handle_message'):
                    if not await handler_info.handler.should_handle_message(message):
                        continue
                
                await handler_info.handler.handle_on_message(message)
                
            except Exception as e:
                handler_info.error_count += 1
                handler_info.last_error = str(e)
                
                BotLogger.error(
                    "MessageDispatch", 
                    f"處理器 {handler_info.name} 錯誤 (第{handler_info.error_count}次): {e}", e
                )
                
                # 如果錯誤次數過多，暫時停用處理器
                if handler_info.error_count >= self.max_errors_per_handler:
                    handler_info.disabled = True
                    BotLogger.warning(
                        "MessageDispatch", 
                        f"處理器 {handler_info.name} 因錯誤過多被暫停 (錯誤次數: {handler_info.error_count})"
                    )
    
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

    @commands.command(name="debug", help="系統除錯資訊 - 用法: ?debug [commands|handlers|listeners]")
    async def debug(self, ctx, debug_type: str = "all"):
        """統一的除錯指令"""
        import discord
        
        debug_type = debug_type.lower()
        
        if debug_type == "commands":
            # 指令診斷
            embed = discord.Embed(title="🔍 指令註冊診斷", color=discord.Color.blue())
            commands_list = []
            for name, command in self.bot.all_commands.items():
                commands_list.append(f"• {name}")
            
            embed.add_field(
                name=f"📋 已註冊指令 ({len(commands_list)})",
                value="\n".join(commands_list[:20]) + ("\n..." if len(commands_list) > 20 else ""),
                inline=False
            )
            
        elif debug_type == "handlers":
            # 處理器診斷
            embed = discord.Embed(title="🔍 訊息處理器診斷", color=discord.Color.green())
            
            if self.handlers:
                handler_info = []
                for h in self.handlers:
                    status = "🔴 已停用" if h.disabled else "🟢 運行中"
                    error_info = f" (錯誤: {h.error_count})" if h.error_count > 0 else ""
                    handler_info.append(f"• {h.name} [P{h.priority}] {status}{error_info}")
                    
                embed.add_field(
                    name=f"🎯 已註冊處理器 ({len(self.handlers)})",
                    value="\n".join(handler_info),
                    inline=False
                )
                
                # 添加統計資訊
                active_count = sum(1 for h in self.handlers if not h.disabled)
                total_errors = sum(h.error_count for h in self.handlers)
                embed.add_field(
                    name="📊 統計",
                    value=f"活躍處理器: {active_count}/{len(self.handlers)}\n"
                          f"總錯誤數: {total_errors}\n"
                          f"處理訊息數: {self.message_count}",
                    inline=True
                )
            else:
                embed.add_field(name="⚠️ 狀態", value="沒有註冊任何處理器", inline=False)
                
        elif debug_type == "listeners":
            # 監聽器診斷
            embed = discord.Embed(title="🔍 監聽器診斷", color=discord.Color.orange())
            
            handle_cogs = []
            for cog_name, cog in self.bot.cogs.items():
                if hasattr(cog, 'handle_on_message'):
                    handle_cogs.append(f"• {cog_name}")
            
            embed.add_field(
                name=f"📋 handle_on_message 方法 ({len(handle_cogs)})",
                value="\n".join(handle_cogs) if handle_cogs else "無",
                inline=False
            )
            
        else:
            # 綜合資訊
            embed = discord.Embed(title="🔍 系統除錯資訊", color=discord.Color.purple())
            embed.add_field(name="📋 指令數量", value=str(len(self.bot.all_commands)), inline=True)
            embed.add_field(name="🎯 處理器數量", value=str(len(self.handlers)), inline=True)
            embed.add_field(name="🏠 Cog 數量", value=str(len(self.bot.cogs)), inline=True)
            embed.add_field(
                name="💡 提示", 
                value="使用 `?debug commands|handlers|listeners` 查看詳細資訊", 
                inline=False
            )
        
        await ctx.send(embed=embed)
        BotLogger.command_used("debug", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"類型: {debug_type}")

    @commands.command(name="logs", help="查看系統日誌 - 用法: ?logs [數量] 或 ?logs stats")
    @commands.has_permissions(manage_messages=True)
    async def view_logs(self, ctx, action_or_limit: str = "10"):
        """查看系統日誌"""
        import discord
        
        if action_or_limit.lower() == "stats":
            # 顯示日誌統計
            stats = BotLogger.get_log_stats()
            if not stats:
                await ctx.send("❌ 無法取得日誌統計資訊")
                return
            
            embed = discord.Embed(title="📊 日誌統計資訊", color=discord.Color.blue())
            embed.add_field(
                name="📋 基本資訊",
                value=f"總日誌數: {stats.get('total_logs', 0)}\n"
                      f"檔案大小: {stats.get('file_size', 0):,} bytes\n"
                      f"最後修改: {stats.get('last_modified', 'N/A')[:19] if stats.get('last_modified') else 'N/A'}",
                inline=False
            )
            
            # 按級別統計
            by_level = stats.get('by_level', {})
            if by_level:
                level_info = "\n".join([f"{level}: {count}" for level, count in by_level.items()])
                embed.add_field(name="📈 按級別統計", value=level_info, inline=True)
            
            # 最近錯誤
            recent_errors = stats.get('recent_errors', [])
            if recent_errors:
                error_info = []
                for err in recent_errors[:3]:  # 只顯示前3個
                    time_str = err.get('timestamp', '')[:16] if err.get('timestamp') else ''
                    error_info.append(f"[{time_str}] {err.get('message', '')[:50]}...")
                embed.add_field(
                    name="🚨 最近錯誤",
                    value="\n".join(error_info) if error_info else "無",
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
        else:
            # 顯示最近的日誌
            try:
                limit = min(int(action_or_limit), 50)  # 最多 50 條
            except ValueError:
                limit = 10
            
            logs = BotLogger.get_json_logs(limit)
            if not logs:
                await ctx.send("❌ 無法取得日誌記錄")
                return
            
            embed = discord.Embed(
                title=f"📝 最近 {len(logs)} 條日誌",
                color=discord.Color.green()
            )
            
            log_lines = []
            for log in logs[-10:]:  # 只顯示最後 10 條
                timestamp = log.get('timestamp', '')[:16]
                level = log.get('level', 'INFO')
                message = log.get('message', '')[:80]
                
                level_emoji = {
                    'DEBUG': '🔍',
                    'INFO': 'ℹ️',
                    'WARNING': '⚠️',
                    'ERROR': '❌',
                    'CRITICAL': '🔥'
                }.get(level, 'ℹ️')
                
                log_lines.append(f"{level_emoji} `{timestamp}` {message}")
            
            embed.description = "\n".join(log_lines)
            embed.set_footer(text=f"共 {len(logs)} 條記錄，使用 ?logs stats 查看統計")
            
            await ctx.send(embed=embed)
        
        BotLogger.command_used("logs", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"查看: {action_or_limit}")


async def setup(bot):
    listener = Listener(bot)
    await bot.add_cog(listener)
