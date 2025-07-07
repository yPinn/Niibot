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
        """全域同步斜線指令"""
        if not self._check_permissions(ctx):
            await self._send_permission_error(ctx)
            return

        if not self._check_command_tree():
            await self._send_error(ctx, "CommandTree 未初始化")
            return

        try:
            # 檢查是否有公會指令存在
            guild_warning = ""
            if ctx.guild:
                guild_obj = discord.Object(id=ctx.guild.id)
                guild_commands = self.bot.tree.get_commands(guild=guild_obj)
                if guild_commands:
                    guild_warning = f"\n⚠️ 檢測到 {len(guild_commands)} 個公會指令，建議先使用 ?reset 清理"
            
            # 執行全域同步
            synced = await self.bot.tree.sync()
            count = len(synced) if synced else 0
            
            response_text = f"✅ 全域同步完成，{count}個指令\n💡 需要1-2小時後在所有伺服器生效{guild_warning}"
            response = await ctx.send(response_text)
            await response.delete(delay=4 if guild_warning else 3)
            
            BotLogger.info("SyncManager", f"全域同步完成 - 指令數: {count}, 執行者: {ctx.author.id}, 公會指令衝突: {bool(guild_warning)}")

        except Exception as e:
            await self._send_error(ctx, f"同步失敗: {str(e)}")
            BotLogger.error("SyncManager", f"同步失敗: {e}", e)

    async def sync_guild_commands(self, ctx: commands.Context, mode: str = "dev"):
        """智能伺服器同步 - 開發模式立即生效"""
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
            guild = discord.Object(id=ctx.guild.id)
            
            if mode == "dev":
                # 開發模式：複製全域指令到公會（立即生效）
                self.bot.tree.copy_global_to(guild=guild)
                synced = await self.bot.tree.sync(guild=guild)
                count = len(synced) if synced else 0
                response = await ctx.send(f"✅ 開發模式：{count}個指令已立即生效\n⚠️ 請記得用 ?reset 清理測試指令")
                await response.delete(delay=3)
                BotLogger.info("SyncManager", f"開發模式同步 - 公會: {ctx.guild.id}, 指令數: {count}")
            
            elif mode == "reset":
                # 重置模式：移除公會指令，回到全域指令
                self.bot.tree.clear_commands(guild=guild)
                await self.bot.tree.sync(guild=guild)
                response = await ctx.send(f"✅ 已重置公會指令，回到全域指令模式")
                await response.delete(delay=2)
                BotLogger.info("SyncManager", f"重置模式完成 - 公會: {ctx.guild.id}")

        except Exception as e:
            await self._send_error(ctx, f"同步失敗: {str(e)}")
            BotLogger.error("SyncManager", f"智能同步失敗: {e}", e)

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
            response = await ctx.send(f"✅ 已清除公會 {guild_id_int} 的所有指令")
            await response.delete(delay=2)
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

    async def check_slash_commands(self, ctx: commands.Context):
        """快速檢查斜線指令狀態"""
        if not self._check_permissions(ctx):
            await self._send_permission_error(ctx)
            return

        if not self._check_command_tree():
            await self._send_error(ctx, "CommandTree 未初始化")
            return

        try:
            # 快速統計斜線指令數量
            global_count = 0
            guild_count = 0
            
            # 統計全域指令
            for cog_name, cog in self.bot.cogs.items():
                if hasattr(cog, '__cog_app_commands__'):
                    global_count += len(cog.__cog_app_commands__)
            global_count += len([cmd for cmd in self.bot.tree.get_commands()])
            
            # 統計公會指令
            if ctx.guild:
                guild_obj = discord.Object(id=ctx.guild.id)
                guild_count = len(self.bot.tree.get_commands(guild=guild_obj))
            
            # 簡潔回應
            status = "✅" if global_count > 0 else "❌"
            guild_status = f"公會: {guild_count}個" if ctx.guild else ""
            
            response = await ctx.send(f"{status} 斜線指令: 全域 {global_count}個 {guild_status}")
            await response.delete(delay=2)
            BotLogger.info("SyncManager", f"指令檢查 - 全域: {global_count}, 公會: {guild_count}, 執行者: {ctx.author.id}")

        except Exception as e:
            await self._send_error(ctx, f"檢查失敗: {str(e)}")
            BotLogger.error("SyncManager", f"指令檢查失敗: {e}", e)


    async def auto_sync_check(self):
        """啟動時檢查是否需要同步"""
        try:
            # 檢查當前載入的斜線指令數量
            expected_commands = 0
            for cog_name, cog in self.bot.cogs.items():
                if hasattr(cog, '__cog_app_commands__'):
                    expected_commands += len(cog.__cog_app_commands__)
            
            if expected_commands > 0:
                BotLogger.info("SyncManager", f"檢測到 {expected_commands} 個斜線指令，建議使用 ?sync 或 ?sg 進行同步")
                return True
            return False
        except Exception as e:
            BotLogger.error("SyncManager", f"自動檢查失敗: {e}", e)
            return False

def setup_sync_manager(bot):
    """設置智能同步管理器"""
    sync_manager = SyncManager(bot)
    
    # 註冊啟動檢查
    @bot.event 
    async def on_ready_sync_check():
        """機器人就緒時檢查同步狀態"""
        await sync_manager.auto_sync_check()

    @bot.command(name="sync")
    async def sync_commands(ctx):
        await sync_manager.sync_commands(ctx)
    
    @bot.command(name="sg")
    async def sync_guild_commands(ctx):
        """開發模式：立即生效斜線指令"""
        await sync_manager.sync_guild_commands(ctx, mode="dev")

    @bot.command(name="reset")
    async def reset_guild_commands(ctx):
        """重置公會指令，回到全域模式"""
        await sync_manager.sync_guild_commands(ctx, mode="reset")

    @bot.command(name="unsync")
    async def unsync_guild(ctx, guild_id: str = None):
        await sync_manager.unsync_guild(ctx, guild_id)

    @bot.command(name="syncstatus")
    async def sync_status(ctx):
        await sync_manager.get_sync_status(ctx)

    @bot.command(name="sc")
    async def slash_check(ctx):
        """快速檢查斜線指令狀態"""
        await sync_manager.check_slash_commands(ctx)

    return sync_manager
