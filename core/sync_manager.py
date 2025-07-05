import time
from typing import Optional

import discord
from discord.ext import commands

from utils.logger import BotLogger


class SyncManager:
    """Discord 斜線指令同步管理器 - 修復版"""

    def __init__(self, bot):
        self.bot = bot
        self._sync_cooldowns = {}  # 同步冷卻追蹤
        self._global_sync_cooldown = 3600  # 全域同步冷卻 1 小時
        self._guild_sync_cooldown = 300   # 伺服器同步冷卻 5 分鐘

    def _check_permissions(self, ctx: commands.Context) -> bool:
        """檢查使用者權限"""
        # 檢查是否為機器人擁有者
        if ctx.author.id == self.bot.owner_id:
            return True

        # 檢查是否在伺服器中且有管理權限
        if ctx.guild:
            member = ctx.guild.get_member(ctx.author.id)
            if member and (member.guild_permissions.manage_guild or member.guild_permissions.administrator):
                return True

        return False

    def _check_bot_permissions(self, guild: Optional[discord.Guild] = None) -> tuple[bool, str]:
        """檢查機器人權限"""
        if not self.bot.user:
            return False, "機器人用戶資訊無法取得"

        if guild:
            # 檢查伺服器中的權限
            bot_member = guild.get_member(self.bot.user.id)
            if not bot_member:
                return False, "機器人不在此伺服器中"

            # 檢查基本權限（管理員或發送訊息權限）
            if not (bot_member.guild_permissions.administrator or
                    bot_member.guild_permissions.send_messages):
                return False, "機器人缺少基本權限（發送訊息或管理員）"

        # 檢查 CommandTree 是否存在
        if not hasattr(self.bot, 'tree') or self.bot.tree is None:
            return False, "CommandTree 未正確初始化"

        return True, "權限檢查通過"

    def _should_sync(self, guild_id: Optional[int] = None) -> tuple[bool, str]:
        """檢查是否應該進行同步（避免頻繁同步）"""
        key = guild_id or "global"
        now = time.time()
        cooldown_time = self._guild_sync_cooldown if guild_id else self._global_sync_cooldown

        if key in self._sync_cooldowns:
            time_passed = now - self._sync_cooldowns[key]
            if time_passed < cooldown_time:
                remaining = int(cooldown_time - time_passed)
                return False, f"冷卻中，還需等待 {remaining} 秒"

        self._sync_cooldowns[key] = now
        return True, "可以進行同步"

    async def _handle_sync_error(self, ctx: commands.Context, error: Exception, operation: str):
        """統一處理同步錯誤"""
        error_type = type(error).__name__

        # 根據錯誤類型提供具體的解決方案
        if isinstance(error, discord.Forbidden):
            error_msg = "權限不足，無法同步指令"
            suggestions = [
                "檢查機器人是否有管理員權限",
                "確認機器人在 OAuth2 設定中有 'applications.commands' 範圍",
                "檢查機器人角色是否被正確設置且有足夠權限"
            ]
        elif isinstance(error, discord.HTTPException):
            if hasattr(error, 'status') and error.status == 429:  # 速率限制
                error_msg = "同步過於頻繁，已被 Discord 限制"
                suggestions = [
                    "請等待一段時間後再試",
                    "避免頻繁使用同步指令",
                    "考慮使用較長的冷卻時間"
                ]
            elif hasattr(error, 'status') and error.status >= 500:  # 伺服器錯誤
                error_msg = "Discord 伺服器暫時無法回應"
                suggestions = [
                    "這是 Discord 的問題，請稍後再試",
                    "檢查 Discord 狀態頁面",
                    "等待 Discord 服務恢復正常"
                ]
            else:
                error_status = getattr(error, 'status', '未知')
                error_text = getattr(error, 'text', str(error))
                error_msg = f"HTTP 錯誤 ({error_status}): {error_text}"
                suggestions = [
                    "檢查網路連線",
                    "確認機器人 Token 是否有效",
                    "聯繫管理員檢查設定"
                ]
        else:
            error_msg = f"{operation}失敗: {str(error)}"
            suggestions = [
                "檢查機器人是否正常運行",
                "確認所有依賴項目都已正確安裝",
                "查看完整錯誤日誌以獲取更多資訊"
            ]

        embed = discord.Embed(
            title=f"❌ {operation}失敗",
            description=error_msg,
            color=discord.Color.red()
        )
        embed.add_field(
            name="🔧 錯誤類型",
            value=f"`{error_type}`",
            inline=True
        )
        embed.add_field(
            name="💡 解決建議",
            value="\n".join(f"• {suggestion}" for suggestion in suggestions),
            inline=False
        )
        embed.set_footer(text="如果問題持續發生，請聯繫技術支援")

        try:
            await ctx.send(embed=embed)
        except discord.HTTPException:
            # 如果無法發送 embed，嘗試發送純文字
            try:
                await ctx.send(f"❌ {error_msg}\n💡 建議: {suggestions[0]}")
            except discord.HTTPException:
                pass  # 如果連純文字都無法發送，可能是更嚴重的權限問題

        # 記錄詳細錯誤
        BotLogger.error(
            "CommandSync", f"{operation}失敗 - {error_type}: {error_msg}", error)

    async def _send_sync_result(self, ctx: commands.Context, synced_count: int, sync_type: str, guild_id: Optional[int] = None):
        """統一發送同步結果"""
        if sync_type == "guild":
            title = "✅ 伺服器同步完成"
            description = f"已同步 {synced_count} 個斜線指令到當前伺服器"
            note = "指令立即生效"
            log_msg = f"公會同步: {synced_count} 個指令 (Guild: {guild_id})"
        elif sync_type == "global":
            title = "✅ 全域同步完成"
            description = f"已全域同步 {synced_count} 個斜線指令"
            note = "需等待 Discord 更新（最多1小時）"
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

        # 添加下次可以同步的時間
        if sync_type != "unsync":
            cooldown = self._global_sync_cooldown if sync_type == "global" else self._guild_sync_cooldown
            next_sync_time = int(time.time()) + cooldown
            embed.add_field(
                name="🕐 下次可同步",
                value=f"<t:{next_sync_time}:R>",
                inline=True
            )

        embed.set_footer(text=f"操作者: {ctx.author.display_name}")

        await ctx.send(embed=embed)

        # 安全的日誌記錄
        try:
            if hasattr(BotLogger, 'command_used'):
                BotLogger.command_used("sync" if sync_type != "unsync" else "unsync",
                                       ctx.author.id,
                                       ctx.guild.id if ctx.guild else 0,
                                       log_msg)
            else:
                BotLogger.info("CommandSync", log_msg)
        except Exception as log_error:
            BotLogger.error("CommandSync", f"日誌記錄失敗: {log_error}")

    async def sync_commands(self, ctx: commands.Context):
        """同步斜線指令 - 在伺服器中自動選擇伺服器同步，否則全域同步"""
        # 檢查使用者權限
        if not self._check_permissions(ctx):
            embed = discord.Embed(
                title="❌ 權限不足",
                description="您沒有使用此指令的權限",
                color=discord.Color.red()
            )
            embed.add_field(
                name="📋 需要權限",
                value="• 機器人擁有者\n• 伺服器管理員\n• 管理伺服器權限",
                inline=False
            )
            await ctx.send(embed=embed)
            return

        # 檢查 CommandTree 是否存在
        if not hasattr(self.bot, 'tree') or self.bot.tree is None:
            embed = discord.Embed(
                title="❌ CommandTree 錯誤",
                description="機器人的 CommandTree 未正確初始化",
                color=discord.Color.red()
            )
            embed.add_field(
                name="🔧 解決方法",
                value="請重新啟動機器人或聯繫開發者",
                inline=False
            )
            await ctx.send(embed=embed)
            return

        status_msg = None

        try:
            if ctx.guild:
                # 在伺服器中 - 執行伺服器同步（即時生效）

                # 檢查機器人權限
                has_permission, permission_msg = self._check_bot_permissions(
                    ctx.guild)
                if not has_permission:
                    embed = discord.Embed(
                        title="❌ 機器人權限不足",
                        description=permission_msg,
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed)
                    return

                # 檢查冷卻
                can_sync, cooldown_msg = self._should_sync(ctx.guild.id)
                if not can_sync:
                    embed = discord.Embed(
                        title="⏱️ 同步冷卻中",
                        description=f"此伺服器{cooldown_msg}",
                        color=discord.Color.orange()
                    )
                    await ctx.send(embed=embed)
                    return

                # 發送同步中的訊息
                try:
                    status_msg = await ctx.send("🔄 正在同步伺服器指令...")
                except discord.HTTPException:
                    pass  # 如果無法發送狀態訊息，繼續執行

                # 執行同步
                guild = discord.Object(id=ctx.guild.id)
                try:
                    synced = await self.bot.tree.sync(guild=guild)
                    synced_count = len(synced) if synced is not None else 0
                except Exception as sync_error:
                    if status_msg:
                        try:
                            await status_msg.delete()
                        except discord.HTTPException:
                            pass
                    raise sync_error

                if status_msg:
                    try:
                        await status_msg.delete()
                    except discord.HTTPException:
                        pass

                await self._send_sync_result(ctx, synced_count, "guild", ctx.guild.id)

            else:
                # 在私訊中 - 執行全域同步

                # 檢查機器人權限
                has_permission, permission_msg = self._check_bot_permissions()
                if not has_permission:
                    embed = discord.Embed(
                        title="❌ 機器人權限不足",
                        description=permission_msg,
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed)
                    return

                # 檢查冷卻
                can_sync, cooldown_msg = self._should_sync()
                if not can_sync:
                    embed = discord.Embed(
                        title="⏱️ 同步冷卻中",
                        description=f"全域同步{cooldown_msg}",
                        color=discord.Color.orange()
                    )
                    await ctx.send(embed=embed)
                    return

                # 發送同步中的訊息
                try:
                    status_msg = await ctx.send("🔄 正在進行全域同步...")
                except discord.HTTPException:
                    pass  # 如果無法發送狀態訊息，繼續執行

                # 執行全域同步
                try:
                    synced = await self.bot.tree.sync()
                    synced_count = len(synced) if synced is not None else 0
                except Exception as sync_error:
                    if status_msg:
                        try:
                            await status_msg.delete()
                        except discord.HTTPException:
                            pass
                    raise sync_error

                if status_msg:
                    try:
                        await status_msg.delete()
                    except discord.HTTPException:
                        pass

                await self._send_sync_result(ctx, synced_count, "global")

        except Exception as e:
            # 刪除狀態訊息（如果存在）
            if status_msg:
                try:
                    await status_msg.delete()
                except discord.HTTPException:
                    pass

            await self._handle_sync_error(ctx, e, "同步指令")

    async def unsync_guild(self, ctx: commands.Context, guild_id: str = None):
        """清除指定公會的斜線指令

        Args:
            guild_id: 指定公會ID，留空則清除當前公會
        """
        # 檢查使用者權限
        if not self._check_permissions(ctx):
            embed = discord.Embed(
                title="❌ 權限不足",
                description="您沒有使用此指令的權限",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        # 檢查 CommandTree 是否存在
        if not hasattr(self.bot, 'tree') or self.bot.tree is None:
            embed = discord.Embed(
                title="❌ CommandTree 錯誤",
                description="機器人的 CommandTree 未正確初始化",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        if guild_id:
            try:
                guild_id_int = int(guild_id)
                guild = discord.Object(id=guild_id_int)
                target_guild = self.bot.get_guild(guild_id_int)
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
            target_guild = ctx.guild

        # 檢查機器人權限
        has_permission, permission_msg = self._check_bot_permissions(
            target_guild)
        if not has_permission:
            embed = discord.Embed(
                title="❌ 機器人權限不足",
                description=permission_msg,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        status_msg = None

        try:
            # 發送清除中的訊息
            try:
                status_msg = await ctx.send("🗑️ 正在清除指令...")
            except discord.HTTPException:
                pass  # 如果無法發送狀態訊息，繼續執行

            # 執行清除
            try:
                self.bot.tree.clear_commands(guild=guild)
                await self.bot.tree.sync(guild=guild)
            except Exception as clear_error:
                if status_msg:
                    try:
                        await status_msg.delete()
                    except discord.HTTPException:
                        pass
                raise clear_error

            if status_msg:
                try:
                    await status_msg.delete()
                except discord.HTTPException:
                    pass

            await self._send_sync_result(ctx, 0, "unsync", guild_id_int)

        except Exception as e:
            # 刪除狀態訊息（如果存在）
            if status_msg:
                try:
                    await status_msg.delete()
                except discord.HTTPException:
                    pass

            await self._handle_sync_error(ctx, e, "清除指令")

    async def get_sync_status(self, ctx: commands.Context):
        """查看同步狀態和冷卻時間"""
        embed = discord.Embed(
            title="📊 同步狀態",
            color=discord.Color.blue()
        )

        now = time.time()

        # 檢查全域同步冷卻
        if "global" in self._sync_cooldowns:
            global_last = self._sync_cooldowns["global"]
            global_remaining = max(
                0, self._global_sync_cooldown - (now - global_last))
            global_status = f"⏱️ 冷卻中 ({int(global_remaining)}秒)" if global_remaining > 0 else "✅ 可用"
        else:
            global_status = "✅ 可用"

        embed.add_field(
            name="🌍 全域同步",
            value=global_status,
            inline=True
        )

        # 檢查當前伺服器同步冷卻
        if ctx.guild:
            guild_key = ctx.guild.id
            if guild_key in self._sync_cooldowns:
                guild_last = self._sync_cooldowns[guild_key]
                guild_remaining = max(
                    0, self._guild_sync_cooldown - (now - guild_last))
                guild_status = f"⏱️ 冷卻中 ({int(guild_remaining)}秒)" if guild_remaining > 0 else "✅ 可用"
            else:
                guild_status = "✅ 可用"

            embed.add_field(
                name="🏠 伺服器同步",
                value=guild_status,
                inline=True
            )

        # 檢查機器人狀態
        has_permission, permission_msg = self._check_bot_permissions(ctx.guild)
        bot_status = "✅ 正常" if has_permission else f"❌ {permission_msg}"

        embed.add_field(
            name="🤖 機器人狀態",
            value=bot_status,
            inline=False
        )

        await ctx.send(embed=embed)


def setup_sync_manager(bot):
    """設置同步管理器並註冊指令"""
    sync_manager = SyncManager(bot)

    @bot.command(name="sync", help="同步斜線指令")
    async def sync_commands(ctx: commands.Context):
        await sync_manager.sync_commands(ctx)

    @bot.command(name="unsync", help="清除公會斜線指令")
    async def unsync_guild(ctx: commands.Context, guild_id: str = None):
        await sync_manager.unsync_guild(ctx, guild_id)

    @bot.command(name="syncstatus", help="查看同步狀態")
    async def sync_status(ctx: commands.Context):
        await sync_manager.get_sync_status(ctx)

    return sync_manager
