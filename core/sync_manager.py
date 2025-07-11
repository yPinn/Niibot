import discord
from discord.ext import commands

from utils.logger import BotLogger


class SyncManager:
    """Discord 斜線指令同步管理器 - 簡化版"""

    def __init__(self, bot):
        self.bot = bot

    def _check_permissions(self, ctx: commands.Context) -> bool:
        """檢查使用者權限"""
        return (ctx.author.id == self.bot.owner_id or 
                (ctx.guild and ctx.author.guild_permissions.manage_guild))

    def _check_command_tree(self) -> bool:
        """檢查 CommandTree 是否可用"""
        return hasattr(self.bot, 'tree') and self.bot.tree is not None


    async def _send_error(self, ctx: commands.Context, message: str):
        """發送簡單錯誤訊息"""
        try:
            await ctx.send(f"❌ {message}")
        except discord.HTTPException:
            pass

    async def _send_success(self, ctx: commands.Context, message: str):
        """發送簡單成功訊息"""
        try:
            await ctx.send(f"✅ {message}")
        except discord.HTTPException:
            pass

    async def sync_commands(self, ctx: commands.Context):
        """同步斜線指令"""
        if not self._check_permissions(ctx):
            await self._send_error(ctx, "權限不足")
            return

        if not self._check_command_tree():
            await self._send_error(ctx, "CommandTree 未初始化")
            return

        try:
            if ctx.guild:
                # 伺服器同步
                guild = discord.Object(id=ctx.guild.id)
                synced = await self.bot.tree.sync(guild=guild)
                count = len(synced) if synced else 0
                await self._send_success(ctx, f"伺服器同步完成，{count}個指令")
            else:
                # 全域同步
                synced = await self.bot.tree.sync()
                count = len(synced) if synced else 0
                await self._send_success(ctx, f"全域同步完成，{count}個指令")

        except Exception as e:
            await self._send_error(ctx, f"同步失敗: {str(e)}")
            BotLogger.error("SyncManager", f"同步失敗: {e}", e)

    async def unsync_guild(self, ctx: commands.Context, guild_id: str = None):
        """清除公會斜線指令"""
        if not self._check_permissions(ctx):
            await self._send_error(ctx, "權限不足")
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

    @bot.command(name="unsync")
    async def unsync_guild(ctx, guild_id: str = None):
        await sync_manager.unsync_guild(ctx, guild_id)

    @bot.command(name="syncstatus")
    async def sync_status(ctx):
        await sync_manager.get_sync_status(ctx)

    return sync_manager
