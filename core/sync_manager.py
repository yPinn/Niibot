import discord
from discord.ext import commands

from utils.logger import BotLogger


class SyncManager:
    """Discord 斜線指令同步管理器 - 簡化版"""

    def __init__(self, bot):
        self.bot = bot

    def _check_permissions(self, ctx: commands.Context) -> bool:
        """檢查使用者權限"""
        from utils.config_manager import config
        admin_ids = config.bot_admin_ids
        
        # 檢查是否為機器人管理員
        if ctx.author.id in admin_ids:
            return True
            
        # 檢查是否為機器人擁有者（如果有設定）
        if self.bot.owner_id and ctx.author.id == self.bot.owner_id:
            return True
            
        # 檢查是否在伺服器中有管理權限
        if ctx.guild and ctx.author.guild_permissions.manage_guild:
            return True
            
        return False

    def _check_command_tree(self) -> bool:
        """檢查 CommandTree 是否可用"""
        return hasattr(self.bot, 'tree') and self.bot.tree is not None


    async def _send_error(self, ctx: commands.Context, message: str):
        """發送簡單錯誤訊息"""
        try:
            await ctx.send(f"❌ {message}")
        except discord.HTTPException:
            pass
    
    async def _send_permission_error(self, ctx: commands.Context):
        """發送權限錯誤訊息"""
        try:
            embed = discord.Embed(
                title="🚫 權限不足",
                description="您沒有執行此指令的權限",
                color=discord.Color.red()
            )
            embed.add_field(
                name="所需權限",
                value="• 機器人管理員\n• 伺服器管理權限 (manage_guild)",
                inline=False
            )
            await ctx.send(embed=embed)
            BotLogger.warning("SyncManager", f"權限不足 - 用戶: {ctx.author.id} ({ctx.author.display_name})")
        except discord.HTTPException:
            await self._send_error(ctx, "權限不足")
            BotLogger.warning("SyncManager", f"權限不足 - 用戶: {ctx.author.id}")

    async def _send_success(self, ctx: commands.Context, message: str):
        """發送簡單成功訊息"""
        try:
            await ctx.send(f"✅ {message}")
        except discord.HTTPException:
            pass

    async def sync_commands(self, ctx: commands.Context):
        """同步斜線指令"""
        if not self._check_permissions(ctx):
            await self._send_permission_error(ctx)
            return

        if not self._check_command_tree():
            await self._send_error(ctx, "CommandTree 未初始化")
            return

        try:
            # 預設執行全域同步，這樣所有指令都會同步
            synced = await self.bot.tree.sync()
            count = len(synced) if synced else 0
            
            if ctx.guild:
                await self._send_success(ctx, f"全域同步完成，{count}個指令 (在伺服器中執行)")
                BotLogger.info("SyncManager", f"全域同步完成 - 指令數: {count}, 執行者: {ctx.author.id}, 執行位置: 公會 {ctx.guild.id}")
            else:
                await self._send_success(ctx, f"全域同步完成，{count}個指令")
                BotLogger.info("SyncManager", f"全域同步完成 - 指令數: {count}, 執行者: {ctx.author.id}, 執行位置: 私訊")

        except Exception as e:
            await self._send_error(ctx, f"同步失敗: {str(e)}")
            BotLogger.error("SyncManager", f"同步失敗: {e}", e)

    async def sync_guild_commands(self, ctx: commands.Context):
        """公會特定同步斜線指令"""
        if not self._check_permissions(ctx):
            await self._send_permission_error(ctx)
            return

        if not self._check_command_tree():
            await self._send_error(ctx, "CommandTree 未初始化")
            return

        if not ctx.guild:
            await self._send_error(ctx, "此指令只能在伺服器中使用")
            return

        try:
            # 公會特定同步
            guild = discord.Object(id=ctx.guild.id)
            synced = await self.bot.tree.sync(guild=guild)
            count = len(synced) if synced else 0
            await self._send_success(ctx, f"伺服器同步完成，{count}個指令")
            BotLogger.info("SyncManager", f"伺服器同步完成 - 公會: {ctx.guild.id}, 指令數: {count}, 執行者: {ctx.author.id}")

        except Exception as e:
            await self._send_error(ctx, f"同步失敗: {str(e)}")
            BotLogger.error("SyncManager", f"公會同步失敗: {e}", e)

    async def unsync_guild(self, ctx: commands.Context, guild_id: str = None):
        """清除公會斜線指令"""
        if not self._check_permissions(ctx):
            await self._send_permission_error(ctx)
            return

        if not self._check_command_tree():
            await self._send_error(ctx, "CommandTree 未初始化")
            return

        if guild_id:
            try:
                guild_id_int = int(guild_id)
                guild = discord.Object(id=guild_id_int)
            except ValueError:
                await self._send_error(ctx, "公會ID必須為數字")
                return
        else:
            if not ctx.guild:
                await self._send_error(ctx, "需在伺服器中使用或提供公會ID")
                return
            guild = discord.Object(id=ctx.guild.id)
            guild_id_int = ctx.guild.id

        try:
            self.bot.tree.clear_commands(guild=guild)
            await self.bot.tree.sync(guild=guild)
            await self._send_success(ctx, f"已清除公會 {guild_id_int} 的所有指令")
        except Exception as e:
            await self._send_error(ctx, f"清除失敗: {str(e)}")
            BotLogger.error("SyncManager", f"清除失敗: {e}", e)

    async def get_sync_status(self, ctx: commands.Context):
        """查看同步狀態"""
        tree_status = "✅ 正常" if self._check_command_tree() else "❌ 未初始化"
        message = f"CommandTree: {tree_status}"
        
        if ctx.guild:
            message += f"\n伺服器: {ctx.guild.name} ({ctx.guild.id})"
        else:
            message += "\n位置: 私訊"
            
        await ctx.send(message)


def setup_sync_manager(bot):
    """設置簡化的同步管理器"""
    sync_manager = SyncManager(bot)

    @bot.command(name="sync")
    async def sync_commands(ctx):
        await sync_manager.sync_commands(ctx)
    
    @bot.command(name="syncguild")
    async def sync_guild_commands(ctx):
        """公會特定同步"""
        await sync_manager.sync_guild_commands(ctx)

    @bot.command(name="unsync")
    async def unsync_guild(ctx, guild_id: str = None):
        await sync_manager.unsync_guild(ctx, guild_id)

    @bot.command(name="syncstatus")
    async def sync_status(ctx):
        await sync_manager.get_sync_status(ctx)

    return sync_manager
