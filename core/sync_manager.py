import discord
from discord.ext import commands
from utils.logger import BotLogger


class SyncManager:
    """Discord 斜線指令同步管理器"""
    
    def __init__(self, bot):
        self.bot = bot
        self._sync_cooldowns = {}  # 同步冷卻追蹤
    
    def _should_sync(self, guild_id: int = None) -> bool:
        """檢查是否應該進行同步（避免頻繁同步）"""
        import time
        key = guild_id or "global"
        now = time.time()
        if key in self._sync_cooldowns and now - self._sync_cooldowns[key] < 30:  # 30秒冷卻
            return False
        self._sync_cooldowns[key] = now
        return True

    async def _handle_sync_error(self, ctx: commands.Context, error: Exception, operation: str):
        """統一處理同步錯誤"""
        error_msg = f"{operation}失敗: {str(error)}"
        
        embed = discord.Embed(
            title="❌ 同步失敗",
            description=error_msg,
            color=discord.Color.red()
        )
        embed.add_field(
            name="💡 可能原因",
            value="• Discord API 暫時無法訪問\n• 權限不足\n• 網路連線問題",
            inline=False
        )
        embed.add_field(
            name="🔄 建議操作",
            value="請稍後再試，或聯繫管理員檢查",
            inline=False
        )
        
        try:
            await ctx.send(embed=embed)
        except discord.HTTPException:
            await ctx.send(error_msg)
        
        BotLogger.error("CommandSync", error_msg, error)

    async def _send_sync_result(self, ctx: commands.Context, synced_count: int, sync_type: str, guild_id: int = None):
        """統一發送同步結果"""
        if sync_type == "guild":
            title = "✅ 伺服器同步完成"
            description = f"已同步 {synced_count} 個斜線指令到當前伺服器"
            note = "指令立即生效"
            log_msg = f"公會同步: {synced_count} 個指令"
        elif sync_type == "global":
            title = "✅ 全域同步完成"
            description = f"已全域同步 {synced_count} 個斜線指令"
            note = "需等待 Discord 更新（約1小時）"
            log_msg = f"全域同步: {synced_count} 個指令"
        else:  # unsync
            title = "✅ 清除完成"
            description = f"已清除公會 {guild_id} 的所有斜線指令"
            note = "指令立即失效"
            log_msg = f"清除公會 {guild_id} 指令"
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.green()
        )
        embed.add_field(
            name="⏰ 生效時間",
            value=note,
            inline=True
        )
        embed.add_field(
            name="📊 同步數量", 
            value=f"{synced_count} 個指令" if sync_type != "unsync" else "全部清除",
            inline=True
        )
        embed.set_footer(text=f"操作者: {ctx.author.display_name}")
        
        await ctx.send(embed=embed)
        BotLogger.command_used("sync" if sync_type != "unsync" else "unsync", 
                              ctx.author.id, 
                              ctx.guild.id if ctx.guild else 0, 
                              log_msg)

    async def sync_commands(self, ctx: commands.Context):
        """同步斜線指令 - 在伺服器中自動選擇伺服器同步，否則全域同步"""
        try:
            if ctx.guild:
                # 在伺服器中 - 執行伺服器同步（即時生效）
                if not self._should_sync(ctx.guild.id):
                    embed = discord.Embed(
                        title="⏱️ 同步冷卻中",
                        description="此伺服器同步冷卻中，請稍後再試",
                        color=discord.Color.orange()
                    )
                    embed.add_field(name="🕐 冷卻時間", value="30秒", inline=True)
                    await ctx.send(embed=embed)
                    return
                    
                guild = discord.Object(id=ctx.guild.id)
                await self.bot.tree.copy_global_to(guild=guild)
                synced = await self.bot.tree.sync(guild=guild)
                await self._send_sync_result(ctx, len(synced), "guild")
            else:
                # 在私訊中 - 執行全域同步
                if not self._should_sync():
                    embed = discord.Embed(
                        title="⏱️ 同步冷卻中",
                        description="全域同步冷卻中，請稍後再試",
                        color=discord.Color.orange()
                    )
                    embed.add_field(name="🕐 冷卻時間", value="30秒", inline=True)
                    await ctx.send(embed=embed)
                    return
                    
                synced = await self.bot.tree.sync()
                await self._send_sync_result(ctx, len(synced), "global")
                    
        except Exception as e:
            await self._handle_sync_error(ctx, e, "同步指令")

    async def unsync_guild(self, ctx: commands.Context, guild_id: str = None):
        """清除指定公會的斜線指令
        
        Args:
            guild_id: 指定公會ID，留空則清除當前公會
        """
        if guild_id:
            try:
                guild_id_int = int(guild_id)
                guild = discord.Object(id=guild_id_int)
            except ValueError:
                embed = discord.Embed(
                    title="❌ 參數錯誤",
                    description="公會ID必須是數字",
                    color=discord.Color.red()
                )
                embed.add_field(
                    name="💡 使用方式",
                    value="`?unsync` - 清除當前伺服器\n`?unsync <公會ID>` - 清除指定伺服器",
                    inline=False
                )
                await ctx.send(embed=embed)
                return
        else:
            if not ctx.guild:
                embed = discord.Embed(
                    title="❌ 使用錯誤",
                    description="此指令只能在伺服器中使用，或提供公會ID",
                    color=discord.Color.red()
                )
                embed.add_field(
                    name="💡 使用方式",
                    value="`?unsync <公會ID>` - 在私訊中使用需提供公會ID",
                    inline=False
                )
                await ctx.send(embed=embed)
                return
            guild = discord.Object(id=ctx.guild.id)
            guild_id_int = ctx.guild.id
        
        try:
            await self.bot.tree.clear_commands(guild=guild)
            await self.bot.tree.sync(guild=guild)
            await self._send_sync_result(ctx, 0, "unsync", guild_id_int)
        except Exception as e:
            await self._handle_sync_error(ctx, e, "清除指令")


def setup_sync_manager(bot):
    """設置同步管理器並註冊指令"""
    sync_manager = SyncManager(bot)
    
    @bot.command(name="sync", help="同步斜線指令")
    async def sync_commands(ctx: commands.Context):
        await sync_manager.sync_commands(ctx)

    @bot.command(name="unsync", help="清除公會斜線指令")
    async def unsync_guild(ctx: commands.Context, guild_id: str = None):
        await sync_manager.unsync_guild(ctx, guild_id)
    
    return sync_manager