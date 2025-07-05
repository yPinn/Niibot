# sync_manager_init_helper.py
# 同步管理器初始化輔助工具

import asyncio

import discord
from discord.ext import commands


class SyncManagerInitHelper:
    """同步管理器初始化輔助工具"""

    @staticmethod
    def ensure_command_tree(bot):
        """確保 CommandTree 正確初始化"""
        if not hasattr(bot, 'tree') or bot.tree is None:
            print("⚠️ 警告：CommandTree 未初始化，正在創建...")
            bot.tree = discord.app_commands.CommandTree(bot)
            print("✅ CommandTree 已創建")
        else:
            print("✅ CommandTree 已存在")

        return bot.tree is not None

    @staticmethod
    async def validate_bot_setup(bot):
        """驗證機器人設置"""
        issues = []

        # 檢查 1: Bot 用戶
        if not bot.user:
            issues.append("機器人用戶資訊不可用（可能未登入）")

        # 檢查 2: CommandTree
        if not hasattr(bot, 'tree') or bot.tree is None:
            issues.append("CommandTree 未初始化")

        # 檢查 3: 應用程式ID
        if not bot.application_id:
            try:
                app_info = await bot.application_info()
                if app_info:
                    bot.application_id = app_info.id
                    print("✅ 應用程式 ID 已設置")
                else:
                    issues.append("無法獲取應用程式資訊")
            except Exception as e:
                issues.append(f"獲取應用程式資訊失敗: {e}")

        return issues

    @staticmethod
    async def safe_sync_test(bot, guild_id=None):
        """安全的同步測試"""
        try:
            # 確保 CommandTree 存在
            if not hasattr(bot, 'tree') or bot.tree is None:
                return False, "CommandTree 未初始化"

            # 執行測試同步
            if guild_id:
                guild = discord.Object(id=guild_id)
                result = await bot.tree.sync(guild=guild)
            else:
                result = await bot.tree.sync()

            # 檢查結果
            if result is None:
                return False, "同步返回 None"

            count = len(result) if hasattr(result, '__len__') else 0
            return True, f"同步成功，{count} 個指令"

        except Exception as e:
            return False, f"同步失敗: {e}"

    @staticmethod
    def create_safe_sync_manager_setup():
        """創建安全的同步管理器設置函數"""

        def safe_setup_sync_manager(bot):
            """安全設置同步管理器並註冊指令"""
            from sync_manager import SyncManager

            # 確保 CommandTree 初始化
            SyncManagerInitHelper.ensure_command_tree(bot)

            # 創建同步管理器
            sync_manager = SyncManager(bot)

            @bot.command(name="sync", help="同步斜線指令")
            async def sync_commands(ctx: commands.Context):
                # 額外的安全檢查
                if not hasattr(bot, 'tree') or bot.tree is None:
                    embed = discord.Embed(
                        title="❌ 系統錯誤",
                        description="CommandTree 未正確初始化",
                        color=discord.Color.red()
                    )
                    embed.add_field(
                        name="🔧 建議解決方案",
                        value="1. 重新啟動機器人\n2. 檢查機器人設置\n3. 聯繫技術支援",
                        inline=False
                    )
                    await ctx.send(embed=embed)
                    return

                await sync_manager.sync_commands(ctx)

            @bot.command(name="unsync", help="清除公會斜線指令")
            async def unsync_guild(ctx: commands.Context, guild_id: str = None):
                # 額外的安全檢查
                if not hasattr(bot, 'tree') or bot.tree is None:
                    embed = discord.Embed(
                        title="❌ 系統錯誤",
                        description="CommandTree 未正確初始化",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed)
                    return

                await sync_manager.unsync_guild(ctx, guild_id)

            @bot.command(name="syncstatus", help="查看同步狀態")
            async def sync_status(ctx: commands.Context):
                await sync_manager.get_sync_status(ctx)

            @bot.command(name="syncdebug", help="同步除錯資訊")
            async def sync_debug(ctx: commands.Context):
                """提供詳細的同步除錯資訊"""
                embed = discord.Embed(
                    title="🔍 同步除錯資訊",
                    color=discord.Color.blue()
                )

                # CommandTree 狀態
                tree_status = "✅ 正常" if (
                    hasattr(bot, 'tree') and bot.tree is not None) else "❌ 未初始化"
                embed.add_field(name="CommandTree",
                                value=tree_status, inline=True)

                # Bot 用戶狀態
                user_status = "✅ 正常" if bot.user else "❌ 未登入"
                embed.add_field(name="Bot 用戶", value=user_status, inline=True)

                # 應用程式 ID
                app_id_status = "✅ 已設置" if bot.application_id else "❌ 未設置"
                embed.add_field(
                    name="應用程式 ID", value=app_id_status, inline=True)

                # Discord.py 版本
                embed.add_field(name="Discord.py 版本",
                                value=discord.__version__, inline=True)

                # 延遲
                latency = f"{round(bot.latency * 1000)}ms" if bot.latency else "未知"
                embed.add_field(name="延遲", value=latency, inline=True)

                # 伺服器數量
                guild_count = len(bot.guilds) if bot.guilds else 0
                embed.add_field(name="伺服器數量", value=str(
                    guild_count), inline=True)

                # 如果在伺服器中，顯示機器人權限
                if ctx.guild:
                    bot_member = ctx.guild.get_member(bot.user.id)
                    if bot_member:
                        perms = bot_member.guild_permissions
                        admin_status = "✅ 是" if perms.administrator else "❌ 否"
                        manage_status = "✅ 是" if perms.manage_guild else "❌ 否"

                        embed.add_field(
                            name="管理員權限", value=admin_status, inline=True)
                        embed.add_field(
                            name="管理伺服器", value=manage_status, inline=True)

                await ctx.send(embed=embed)

            return sync_manager

        return safe_setup_sync_manager


# 使用範例
def create_bot_with_safe_sync():
    """創建帶有安全同步功能的機器人"""

    # 創建機器人
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix='?', intents=intents)

    @bot.event
    async def on_ready():
        print(f'{bot.user} 已上線！')

        # 驗證設置
        issues = await SyncManagerInitHelper.validate_bot_setup(bot)

        if issues:
            print("⚠️ 發現以下問題：")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("✅ 所有檢查都通過")

        # 設置同步管理器
        safe_setup = SyncManagerInitHelper.create_safe_sync_manager_setup()
        sync_manager = safe_setup(bot)
        print("✅ 安全同步管理器已設置")

    return bot


# 獨立的修復工具
async def fix_command_tree_issues(bot):
    """修復 CommandTree 相關問題"""
    print("🔧 正在檢查並修復 CommandTree 問題...")

    fixed_issues = []

    # 1. 確保 CommandTree 存在
    if not hasattr(bot, 'tree') or bot.tree is None:
        bot.tree = discord.app_commands.CommandTree(bot)
        fixed_issues.append("創建了新的 CommandTree")

    # 2. 檢查應用程式 ID
    if not bot.application_id and bot.user:
        try:
            app_info = await bot.application_info()
            if app_info:
                bot.application_id = app_info.id
                fixed_issues.append("設置了應用程式 ID")
        except Exception as e:
            print(f"⚠️ 無法設置應用程式 ID: {e}")

    # 3. 測試 CommandTree 功能
    try:
        # 嘗試獲取現有指令
        commands = bot.tree.get_commands()
        fixed_issues.append(f"CommandTree 正常運作 ({len(commands)} 個指令)")
    except Exception as e:
        print(f"⚠️ CommandTree 測試失敗: {e}")

    if fixed_issues:
        print("✅ 已修復以下問題：")
        for fix in fixed_issues:
            print(f"  - {fix}")
    else:
        print("ℹ️ 沒有發現需要修復的問題")

    return len(fixed_issues) > 0
