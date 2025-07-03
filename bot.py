import asyncio
import os
import math
from typing import Dict, List, Any
from datetime import datetime

import discord
from discord.ext import commands

from utils import util
from utils.util import create_activity, ensure_data_dir, get_deployment_info, get_version_info, get_uptime_info
from utils.logger import BotLogger
from utils.config_manager import config

ENV = config.get('BOT_ENV', 'local')

# 初始化日誌系統
BotLogger.initialize(config.log_level, config.log_file)

# 確保資料目錄存在
ensure_data_dir()

# keep_alive 將在 main() 函數中啟動

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=config.command_prefix, intents=intents)

# 機器人啟動時間記錄
startup_time = None

# 同步狀態追蹤
_sync_cooldowns = {}

def _should_sync(guild_id: int = None) -> bool:
    """檢查是否應該進行同步（避免頻繁同步）"""
    import time
    key = guild_id or "global"
    now = time.time()
    if key in _sync_cooldowns and now - _sync_cooldowns[key] < 30:  # 30秒冷卻
        return False
    _sync_cooldowns[key] = now
    return True

# 同步相關輔助函數
async def _handle_sync_error(ctx: commands.Context, error: Exception, operation: str):
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

async def _send_sync_result(ctx: commands.Context, synced_count: int, sync_type: str, guild_id: int = None):
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

# 設定斜線指令同步
@bot.command(name="sync", help="同步斜線指令")
async def sync_commands(ctx: commands.Context):
    """同步斜線指令 - 在伺服器中自動選擇伺服器同步，否則全域同步"""
    try:
        if ctx.guild:
            # 在伺服器中 - 執行伺服器同步（即時生效）
            if not _should_sync(ctx.guild.id):
                embed = discord.Embed(
                    title="⏱️ 同步冷卻中",
                    description="此伺服器同步冷卻中，請稍後再試",
                    color=discord.Color.orange()
                )
                embed.add_field(name="🕐 冷卻時間", value="30秒", inline=True)
                await ctx.send(embed=embed)
                return
                
            guild = discord.Object(id=ctx.guild.id)
            await bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            await _send_sync_result(ctx, len(synced), "guild")
        else:
            # 在私訊中 - 執行全域同步
            if not _should_sync():
                embed = discord.Embed(
                    title="⏱️ 同步冷卻中",
                    description="全域同步冷卻中，請稍後再試",
                    color=discord.Color.orange()
                )
                embed.add_field(name="🕐 冷卻時間", value="30秒", inline=True)
                await ctx.send(embed=embed)
                return
                
            synced = await bot.tree.sync()
            await _send_sync_result(ctx, len(synced), "global")
                
    except Exception as e:
        await _handle_sync_error(ctx, e, "同步指令")

@bot.command(name="unsync", help="清除公會斜線指令")
async def unsync_guild(ctx: commands.Context, guild_id: str = None):
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
        await bot.tree.clear_commands(guild=guild)
        await bot.tree.sync(guild=guild)
        await _send_sync_result(ctx, 0, "unsync", guild_id_int)
    except Exception as e:
        await _handle_sync_error(ctx, e, "清除指令")

# 指令禁用系統
_disabled_commands = {}  # {指令名稱: 禁用原因}
_disabled_commands_file = "disabled_commands.json"

async def _load_disabled_commands():
    """載入禁用指令列表"""
    global _disabled_commands
    try:
        from utils import util
        file_path = util.get_data_file_path(_disabled_commands_file)
        _disabled_commands = await util.read_json(file_path)
        if not isinstance(_disabled_commands, dict):
            _disabled_commands = {}
        BotLogger.info("CommandDisable", f"載入 {len(_disabled_commands)} 個禁用指令")
    except Exception as e:
        BotLogger.warning("CommandDisable", f"載入禁用指令列表失敗: {e}")
        _disabled_commands = {}

async def _save_disabled_commands():
    """儲存禁用指令列表"""
    try:
        from utils import util
        file_path = util.get_data_file_path(_disabled_commands_file)
        await util.write_json(file_path, _disabled_commands)
    except Exception as e:
        BotLogger.error("CommandDisable", f"儲存禁用指令列表失敗: {e}")

async def _check_command_enabled(ctx):
    """檢查指令是否被禁用"""
    if ctx.command is None:
        return True
    
    command_name = ctx.command.qualified_name
    if command_name in _disabled_commands:
        reason = _disabled_commands[command_name]
        
        # 創建更詳細的禁用提示 embed
        embed = discord.Embed(
            title="🚫 指令被禁用",
            description=f"指令 `{command_name}` 目前無法使用",
            color=discord.Color.red()
        )
        
        embed.add_field(
            name="📝 禁用原因",
            value=reason,
            inline=False
        )
        
        embed.add_field(
            name="💡 說明",
            value="如需啟用此指令，請聯繫管理員",
            inline=False
        )
        
        embed.set_footer(text=f"請求者: {ctx.author.display_name}")
        
        try:
            await ctx.send(embed=embed)
        except discord.HTTPException:
            # 如果 embed 發送失敗，使用簡單訊息
            await ctx.send(f"❌ 指令 `{command_name}` 目前被禁用\n原因: {reason}")
        
        BotLogger.info("CommandDisable", f"用戶 {ctx.author.display_name} ({ctx.author.id}) 嘗試使用被禁用的指令: {command_name}")
        return False
    return True

# 添加全域指令檢查
bot.add_check(_check_command_enabled)

@bot.command(name="disable", help="禁用指令")
async def disable_command(ctx: commands.Context, command_name: str, *, reason: str = "管理員禁用"):
    """禁用指定指令
    
    Args:
        command_name: 要禁用的指令名稱
        reason: 禁用原因
    """
    # 防止禁用關鍵管理指令
    protected_commands = ["disable", "enable", "sys"]
    if command_name in protected_commands:
        embed = discord.Embed(
            title="🛡️ 受保護指令",
            description=f"指令 `{command_name}` 是系統核心指令，無法被禁用",
            color=discord.Color.orange()
        )
        embed.add_field(
            name="🔒 受保護指令列表",
            value="• `disable` - 禁用指令管理\n• `enable` - 啟用指令管理\n• `sys` - 系統狀態檢查",
            inline=False
        )
        await ctx.send(embed=embed)
        return
    
    # 檢查指令是否存在
    command = bot.get_command(command_name)
    if not command:
        # 提供相似指令建議
        all_commands = [cmd.name for cmd in bot.commands]
        suggestions = [cmd for cmd in all_commands if command_name.lower() in cmd.lower() or cmd.lower() in command_name.lower()]
        
        embed = discord.Embed(
            title="❌ 指令不存在",
            description=f"找不到指令: `{command_name}`",
            color=discord.Color.red()
        )
        
        if suggestions:
            embed.add_field(
                name="💡 相似指令建議",
                value="\n".join([f"• `{cmd}`" for cmd in suggestions[:5]]),
                inline=False
            )
        
        embed.add_field(
            name="📝 提示",
            value="使用 `?help` 查看所有可用指令",
            inline=False
        )
        
        await ctx.send(embed=embed)
        return
    
    # 檢查指令是否已被禁用
    if command_name in _disabled_commands:
        embed = discord.Embed(
            title="⚠️ 指令已被禁用",
            description=f"指令 `{command_name}` 已經被禁用",
            color=discord.Color.orange()
        )
        embed.add_field(
            name="📝 當前禁用原因",
            value=_disabled_commands[command_name],
            inline=False
        )
        embed.add_field(
            name="💡 操作選項",
            value=f"如需修改原因，請先使用 `?enable {command_name}` 然後重新禁用",
            inline=False
        )
        await ctx.send(embed=embed)
        return
    
    # 禁用指令
    _disabled_commands[command_name] = reason
    await _save_disabled_commands()
    
    embed = discord.Embed(
        title="✅ 指令已禁用",
        description=f"成功禁用指令 `{command_name}`",
        color=discord.Color.green()
    )
    embed.add_field(
        name="📝 禁用原因",
        value=reason,
        inline=False
    )
    embed.add_field(
        name="🔄 恢復方式",
        value=f"使用 `?enable {command_name}` 重新啟用",
        inline=False
    )
    embed.set_footer(text=f"操作者: {ctx.author.display_name}")
    
    await ctx.send(embed=embed)
    BotLogger.command_used("disable", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"禁用指令: {command_name} - 原因: {reason}")

@bot.command(name="enable", help="啟用指令")
async def enable_command(ctx: commands.Context, command_name: str):
    """啟用指定指令
    
    Args:
        command_name: 要啟用的指令名稱
    """
    if command_name not in _disabled_commands:
        embed = discord.Embed(
            title="ℹ️ 指令狀態",
            description=f"指令 `{command_name}` 目前未被禁用",
            color=discord.Color.blue()
        )
        
        # 檢查指令是否存在
        command = bot.get_command(command_name)
        if command:
            embed.add_field(
                name="✅ 指令狀態",
                value="此指令正常可用，無需啟用",
                inline=False
            )
        else:
            embed.add_field(
                name="❌ 指令狀態", 
                value="此指令不存在於系統中",
                inline=False
            )
            
        embed.add_field(
            name="📋 查看禁用列表",
            value="使用 `?disabled` 查看所有被禁用的指令",
            inline=False
        )
        
        await ctx.send(embed=embed)
        return
    
    # 記錄原因用於日誌
    original_reason = _disabled_commands[command_name]
    
    # 啟用指令
    del _disabled_commands[command_name]
    await _save_disabled_commands()
    
    embed = discord.Embed(
        title="✅ 指令已啟用",
        description=f"成功啟用指令 `{command_name}`",
        color=discord.Color.green()
    )
    embed.add_field(
        name="📝 原禁用原因",
        value=original_reason,
        inline=False
    )
    embed.add_field(
        name="🎯 當前狀態",
        value="指令現在可以正常使用",
        inline=False
    )
    embed.set_footer(text=f"操作者: {ctx.author.display_name}")
    
    await ctx.send(embed=embed)
    BotLogger.command_used("enable", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"啟用指令: {command_name} - 原因: {original_reason}")

@bot.command(name="disabled", help="查看被禁用的指令")
async def list_disabled_commands(ctx: commands.Context):
    """查看當前被禁用的指令列表"""
    if not _disabled_commands:
        embed = discord.Embed(
            title="✅ 指令狀態良好",
            description="目前沒有被禁用的指令",
            color=discord.Color.green()
        )
        embed.add_field(
            name="🎯 系統狀態",
            value="所有指令都正常可用",
            inline=False
        )
        embed.add_field(
            name="🔧 管理指令",
            value="• `?disable <指令名> [原因]` - 禁用指令\n• `?enable <指令名>` - 啟用指令",
            inline=False
        )
        await ctx.send(embed=embed)
        return
    
    embed = discord.Embed(
        title="🚫 被禁用的指令",
        description=f"共有 {len(_disabled_commands)} 個指令被禁用",
        color=discord.Color.red()
    )
    
    # 按字母順序排序
    sorted_commands = sorted(_disabled_commands.items())
    
    for cmd_name, reason in sorted_commands:
        embed.add_field(
            name=f"🔒 `{cmd_name}`",
            value=f"**原因:** {reason}\n**啟用:** `?enable {cmd_name}`",
            inline=False
        )
    
    embed.add_field(
        name="💡 批量管理",
        value="如需啟用多個指令，請逐一使用 `?enable` 指令",
        inline=False
    )
    
    embed.set_footer(text=f"查詢者: {ctx.author.display_name}")
    
    await ctx.send(embed=embed)
    BotLogger.command_used("disabled", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"查看 {len(_disabled_commands)} 個禁用指令")

BotLogger.system_event("機器人初始化", f"環境: {ENV}, 前綴: {config.command_prefix}")


@bot.event
async def on_ready():
    global startup_time
    startup_time = datetime.now(datetime.UTC)
    
    try:
        BotLogger.warning("BotMain", f"🤖 機器人上線: {bot.user} (環境: {ENV})")
        
        try:
            activity = create_activity()
            await bot.change_presence(status=getattr(discord.Status, config.status), activity=activity)
            BotLogger.system_event("狀態設定", f"狀態: {config.status}, 活動: {config.activity_name}")
        except Exception as e:
            BotLogger.error("BotStatus", "設定機器人狀態失敗", e)
        
        # 載入禁用指令列表
        await _load_disabled_commands()
        
        BotLogger.system_event("機器人就緒", "所有初始化完成")
        
    except Exception as e:
        BotLogger.error("BotMain", "on_ready 執行失敗", e)

@bot.event
async def on_message(message):
    """全域訊息處理 - 覆蓋Discord.py內建機制"""
    if message.author.bot:
        return
    
    # 處理自定義handler（如果listener已載入）
    if 'Listener' in bot.cogs:
        listener = bot.cogs['Listener']
        for handler in listener.handlers:
            try:
                await handler.handle_on_message(message)
            except Exception as e:
                BotLogger.error("GlobalHandler", f"處理器錯誤: {e}")
    
    # 處理Discord指令（只調用一次）
    await bot.process_commands(message)


# Cog 管理指令群組
@bot.group(name="cog", invoke_without_subcommand=True)
async def cog_group(ctx):
    """Cog 管理指令群組"""
    if ctx.invoked_subcommand is None:
        embed = discord.Embed(
            title="🔧 Cog 管理指令",
            description="管理機器人模組的載入、卸載和重載",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📥 載入指令",
            value="`?cog load <名稱>` 或 `?l <名稱>`\n載入指定的 Cog 模組",
            inline=False
        )
        
        embed.add_field(
            name="📤 卸載指令", 
            value="`?cog unload <名稱>` 或 `?u <名稱>`\n卸載指定的 Cog 模組",
            inline=False
        )
        
        embed.add_field(
            name="🔄 重載指令",
            value="`?cog reload <名稱>` 或 `?rl <名稱>`\n重新載入指定的 Cog 模組",
            inline=False
        )
        
        embed.add_field(
            name="🔄 全部重載",
            value="`?cog reload_all` 或 `?rla`\n重新載入所有 Cog 模組",
            inline=False
        )
        
        embed.set_footer(text="💡 舊指令 ?l, ?u, ?rl, ?rla 仍可使用")
        await ctx.send(embed=embed)

@cog_group.command(name="load", aliases=["l"])
async def cog_load(ctx, extension):
    """載入指定的 Cog 模組"""
    try:
        await bot.load_extension(f"cogs.{extension}")
        await ctx.send(f"✅ 載入: {extension}")
        BotLogger.command_used("cog.load", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"載入: {extension}")
    except Exception as e:
        error_msg = f"載入 {extension} 失敗: {str(e)}"
        await ctx.send(f"❌ {error_msg}")
        BotLogger.error("CogLoader", error_msg, e)

@cog_group.command(name="unload", aliases=["u"])
async def cog_unload(ctx, extension):
    """卸載指定的 Cog 模組"""
    try:
        await bot.unload_extension(f"cogs.{extension}")
        await ctx.send(f"✅ 卸載: {extension}")
        BotLogger.command_used("cog.unload", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"卸載: {extension}")
    except Exception as e:
        error_msg = f"卸載 {extension} 失敗: {str(e)}"
        await ctx.send(f"❌ {error_msg}")
        BotLogger.error("CogLoader", error_msg, e)

# 向後相容的獨立指令
@bot.command(name="l", help="load cog (alias for ?cog load)")
async def load_compat(ctx, extension):
    """載入 Cog - 向後相容指令"""
    await cog_load(ctx, extension)

@bot.command(name="u", help="unload cog (alias for ?cog unload)")
async def unload_compat(ctx, extension):
    """卸載 Cog - 向後相容指令"""
    await cog_unload(ctx, extension)

@bot.command(name="test")
async def test_command(ctx):
    """測試指令 - 顯示機器人狀態和部署信息"""
    BotLogger.info("TestCommand", f"測試指令執行 - 用戶: {ctx.author.id}")
    
    try:
        deployment_info = get_deployment_info()
        version_info = get_version_info()
        uptime_info = get_uptime_info(startup_time)
        
        embed = discord.Embed(
            title="🤖 機器人測試",
            description="機器人運行正常",
            color=0x00ff00
        )
        
        embed.add_field(
            name="📦 版本資訊",
            value=f"```{version_info}```",
            inline=False
        )
        
        embed.add_field(
            name="⏰ 運行資訊",
            value=f"```{uptime_info}```",
            inline=False
        )
        
        embed.add_field(
            name="📍 部署資訊",
            value=f"```{deployment_info}```",
            inline=False
        )
        
        embed.add_field(
            name="⚡ 即時狀態",
            value=f"延遲: {round(bot.latency * 1000)}ms\n伺服器數量: {len(bot.guilds)}\n載入的 Cogs: {len(bot.cogs)}",
            inline=True
        )
        
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text=f"請求者: {ctx.author.display_name}")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        BotLogger.error("TestCommand", "測試指令執行失敗", e)
        await ctx.send(f"✅ 測試完成（簡化模式）\n環境: {ENV}")


@bot.command(name="sys", aliases=["system"])
async def system_status(ctx):
    """快速系統狀態檢查 - 精簡版機器人健康狀態"""
    BotLogger.info("SystemStatus", f"系統狀態查詢 - 用戶: {ctx.author.id}")
    
    try:
        # 計算運行時間
        uptime_str = ""
        if startup_time:
            from datetime import datetime
            current_time = datetime.now(datetime.UTC)
            uptime = current_time - startup_time
            days = uptime.days
            hours, remainder = divmod(uptime.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            
            if days > 0:
                uptime_str = f"{days}天 {hours}小時 {minutes}分鐘"
            elif hours > 0:
                uptime_str = f"{hours}小時 {minutes}分鐘"
            else:
                uptime_str = f"{minutes}分鐘"
        else:
            uptime_str = "未知"
        
        # 基本狀態檢查
        latency = round(bot.latency * 1000)
        guild_count = len(bot.guilds)
        cog_count = len(bot.cogs)
        
        # 狀態顏色判斷
        if latency < 100:
            color = 0x00ff00  # 綠色 - 良好
        elif latency < 300:
            color = 0xffff00  # 黃色 - 普通
        else:
            color = 0xff0000  # 紅色 - 較差
        
        embed = discord.Embed(
            title="⚡ 系統狀態",
            description="機器人系統健康狀況",
            color=color
        )
        
        # 核心狀態
        embed.add_field(
            name="🔄 運行狀態",
            value=f"環境: {ENV}\n運行時間: {uptime_str}\n延遲: {latency}ms",
            inline=True
        )
        
        # 服務狀態
        deployment_info = get_deployment_info()
        try:
            python_version = deployment_info.split('Python: ')[1].split(' | ')[0] if 'Python:' in deployment_info else 'unknown'
        except (IndexError, AttributeError):
            python_version = 'unknown'
            
        embed.add_field(
            name="📊 服務統計",
            value=f"伺服器: {guild_count}\nCogs: {cog_count}\nPython: {python_version}",
            inline=True
        )
        
        # 版本資訊（簡化）
        try:
            import subprocess
            result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], 
                                  capture_output=True, text=True, timeout=3)
            commit_hash = result.stdout.strip() if result.returncode == 0 else "unknown"
        except:
            commit_hash = "unknown"
        
        embed.add_field(
            name="📦 版本",
            value=f"Commit: {commit_hash}",
            inline=True
        )
        
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text=f"系統檢查 • 請求者: {ctx.author.display_name}")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        BotLogger.error("SystemStatus", "系統狀態查詢失敗", e)
        await ctx.send(f"⚡ 系統運行中\n環境: {ENV}\n延遲: {round(bot.latency * 1000)}ms")


class HelpPaginationView(discord.ui.View):
    """幫助系統分頁介面"""
    
    def __init__(self, categories: Dict[str, List[Dict[str, str]]], bot_instance, timeout=300):
        super().__init__(timeout=timeout)
        self.categories = categories
        self.bot = bot_instance
        self.current_page = 0
        self.category_names = list(categories.keys())
        self.max_pages = len(self.category_names)
        
        # 更新按鈕狀態
        self.update_buttons()
    
    def update_buttons(self):
        """更新按鈕的啟用/禁用狀態"""
        self.prev_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= self.max_pages - 1
        
        # 更新頁面顯示按鈕的標籤
        self.page_button.label = f"{self.current_page + 1}/{self.max_pages}"
    
    def create_embed(self) -> discord.Embed:
        """創建當前頁面的embed"""
        if not self.category_names or self.current_page >= len(self.category_names):
            return self.create_overview_embed()
        
        category_name = self.category_names[self.current_page]
        commands = self.categories[category_name]
        
        # 轉換cog名稱為中文顯示名稱
        display_names = {
            'Reply': '🎭 回覆系統',
            'Party': '👥 分隊系統', 
            'Eat': '🍽️ 用餐推薦',
            'Draw': '🎲 抽獎系統',
            'Clock': '⏰ 打卡系統',
            'Clear': '🧹 清理工具',
            'Emojitool': '😊 表情工具',
            'Repo': '🎯 準心庫',
            'Tinder': '💕 配對系統',
            'TwitterMonitor': '🐦 Twitter監控',
            '系統指令': '⚙️ 系統指令'
        }
        
        display_name = display_names.get(category_name, f"📦 {category_name}")
        
        embed = discord.Embed(
            title=f"📚 {display_name}",
            description=f"第 {self.current_page + 1} 頁，共 {self.max_pages} 頁",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        # 添加指令列表
        if commands:
            commands_text = []
            for cmd in commands:
                commands_text.append(f"`/{cmd['name']}` - {cmd['description']}")
            
            embed.add_field(
                name="📋 可用指令",
                value="\n".join(commands_text) if commands_text else "此分類暫無可用指令",
                inline=False
            )
        
        # 添加特殊說明
        special_info = self.get_category_special_info(category_name)
        if special_info:
            embed.add_field(
                name="💡 特殊說明",
                value=special_info,
                inline=False
            )
        
        embed.set_footer(
            text="Niibot • 使用導覽按鈕瀏覽不同功能分類",
            icon_url=self.bot.user.display_avatar.url if self.bot.user else None
        )
        
        return embed
    
    def get_category_special_info(self, category_name: str) -> str:
        """獲取分類的特殊說明信息"""
        special_info = {
            'Reply': "• copycat指令可複製用戶頭像、橫幅和主題顏色\n• 支援切換伺服器專用設定和全域設定\n• 別名：`cc`、`複製`、`ditto`",
            'Party': "• 快速建立分隊並管理成員\n• 支援語音頻道連動功能",
            'Eat': "• 隨機推薦餐廳或食物\n• 可按分類篩選（如日式、中式等）",
            'Clock': "• 記錄每日打卡時間\n• 統計個人和團體數據",
            'Draw': "• 支援多種抽獎模式\n• 可設定獎品和中獎機率",
            'Clear': "• 批量刪除訊息功能\n• 支援按用戶、時間範圍篩選"
        }
        return special_info.get(category_name, "")
    
    def create_overview_embed(self) -> discord.Embed:
        """創建總覽頁面"""
        embed = discord.Embed(
            title="📚 Niibot 指令總覽",
            description="選擇下方按鈕瀏覽各功能分類，或使用導覽按鈕切換頁面",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        
        # 統計信息
        total_commands = sum(len(cmds) for cmds in self.categories.values())
        embed.add_field(
            name="📊 統計信息",
            value=f"• 功能分類：{len(self.categories)} 個\n• 指令總數：{total_commands} 個",
            inline=False
        )
        
        # 快速導覽
        category_list = []
        for i, category_name in enumerate(self.category_names):
            display_names = {
                'Reply': '🎭 回覆系統',
                'Party': '👥 分隊系統', 
                'Eat': '🍽️ 用餐推薦',
                'Draw': '🎲 抽獎系統',
                'Clock': '⏰ 打卡系統',
                'Clear': '🧹 清理工具',
                'Emojitool': '😊 表情工具',
                'Repo': '🎯 準心庫',
                'Tinder': '💕 配對系統',
                'TwitterMonitor': '🐦 Twitter監控',
                '系統指令': '⚙️ 系統指令'
            }
            display_name = display_names.get(category_name, f"📦 {category_name}")
            cmd_count = len(self.categories[category_name])
            category_list.append(f"{i+1}. {display_name} ({cmd_count} 個指令)")
        
        embed.add_field(
            name="🗂️ 功能分類",
            value="\n".join(category_list),
            inline=False
        )
        
        embed.add_field(
            name="💡 使用提示",
            value="• 斜線指令以 `/` 開頭\n• 傳統指令以 `?` 開頭\n• 使用 `?help` 查看傳統指令\n• 點擊下方按鈕快速跳轉到特定分類",
            inline=False
        )
        
        embed.set_footer(
            text="Niibot • 點擊導覽按鈕開始探索",
            icon_url=self.bot.user.display_avatar.url if self.bot.user else None
        )
        
        return embed
    
    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.secondary, disabled=True)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """上一頁按鈕"""
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            embed = self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="1/1", style=discord.ButtonStyle.primary, disabled=True)
    async def page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """頁面顯示按鈕（點擊返回總覽）"""
        embed = self.create_overview_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="➡️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """下一頁按鈕"""
        if self.current_page < self.max_pages - 1:
            self.current_page += 1
            self.update_buttons()
            embed = self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.select(
        placeholder="🔍 快速跳轉到功能分類...",
        options=[
            discord.SelectOption(label="總覽頁面", value="overview", emoji="📚"),
        ]
    )
    async def category_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        """分類選擇下拉選單"""
        selected_value = select.values[0]
        
        if selected_value == "overview":
            embed = self.create_overview_embed()
        else:
            # 找到對應的分類索引
            try:
                category_index = int(selected_value)
                if 0 <= category_index < len(self.category_names):
                    self.current_page = category_index
                    self.update_buttons()
                    embed = self.create_embed()
                else:
                    embed = self.create_overview_embed()
            except (ValueError, IndexError):
                embed = self.create_overview_embed()
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    def update_select_options(self):
        """更新下拉選單選項"""
        options = [discord.SelectOption(label="📚 總覽頁面", value="overview", emoji="🏠")]
        
        display_names = {
            'Reply': '🎭 回覆系統',
            'Party': '👥 分隊系統', 
            'Eat': '🍽️ 用餐推薦',
            'Draw': '🎲 抽獎系統',
            'Clock': '⏰ 打卡系統',
            'Clear': '🧹 清理工具',
            'Emojitool': '😊 表情工具',
            'Repo': '🎯 準心庫',
            'Tinder': '💕 配對系統',
            'TwitterMonitor': '🐦 Twitter監控',
            '系統指令': '⚙️ 系統指令'
        }
        
        for i, category_name in enumerate(self.category_names):
            if len(options) >= 25:  # Discord限制最多25個選項
                break
            display_name = display_names.get(category_name, category_name)
            cmd_count = len(self.categories[category_name])
            options.append(
                discord.SelectOption(
                    label=f"{display_name} ({cmd_count}個)",
                    value=str(i),
                    description=f"查看{display_name}的所有指令"
                )
            )
        
        self.category_select.options = options
    
    async def on_timeout(self):
        """View逾時處理"""
        for item in self.children:
            item.disabled = True
        
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=self)
        except:
            pass


# 斜線指令版本的help
@bot.tree.command(name="help", description="顯示所有可用的斜線指令")
async def slash_help(interaction: discord.Interaction):
    """斜線指令版本的幫助指令 - 分頁式介面"""
    try:
        # 收集所有斜線指令
        commands_by_cog = {}
        
        # 遍歷所有已載入的cogs
        for cog_name, cog in bot.cogs.items():
            cog_commands = []
            
            # 獲取cog中的斜線指令
            if hasattr(cog, '__cog_app_commands__'):
                for command in cog.__cog_app_commands__:
                    if hasattr(command, 'name') and hasattr(command, 'description'):
                        cog_commands.append({
                            'name': command.name,
                            'description': command.description
                        })
            
            if cog_commands:
                commands_by_cog[cog_name] = cog_commands
        
        # 添加bot級別的斜線指令
        bot_commands = []
        for command in bot.tree.get_commands():
            if hasattr(command, 'name') and hasattr(command, 'description'):
                # 檢查是否已在cog中列出
                found_in_cog = False
                for cog_cmds in commands_by_cog.values():
                    if any(cmd['name'] == command.name for cmd in cog_cmds):
                        found_in_cog = True
                        break
                
                if not found_in_cog:
                    bot_commands.append({
                        'name': command.name,
                        'description': command.description
                    })
        
        if bot_commands:
            commands_by_cog['系統指令'] = bot_commands
        
        # 創建分頁視圖
        view = HelpPaginationView(commands_by_cog, bot)
        view.update_select_options()  # 更新下拉選單選項
        
        # 創建初始embed（總覽頁面）
        embed = view.create_overview_embed()
        
        # 發送訊息
        await interaction.response.send_message(embed=embed, view=view)
        
        # 保存訊息reference給view使用
        message = await interaction.original_response()
        view.message = message
        
        # 記錄指令使用
        total_commands = sum(len(cmds) for cmds in commands_by_cog.values())
        BotLogger.command_used(
            "help",
            interaction.user.id,
            interaction.guild.id if interaction.guild else 0,
            f"查看分頁式指令列表，共 {total_commands} 個指令"
        )
        
    except Exception as e:
        BotLogger.error("SlashHelp", f"分頁式help指令執行失敗", e)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    "❌ 獲取指令列表時發生錯誤，請稍後再試",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ 獲取指令列表時發生錯誤，請稍後再試",
                    ephemeral=True
                )
        except:
            pass


@cog_group.command(name="reload", aliases=["rl"])
async def cog_reload(ctx, extension):
    """重新載入指定的 Cog 模組"""
    try:
        await bot.reload_extension(f"cogs.{extension}")
        
        # 如果重載的不是 listener，且 listener 已載入，則重新觸發處理器註冊
        if extension != "listener" and "cogs.listener" in bot.extensions:
            listener_cog = bot.get_cog("Listener")
            if listener_cog and hasattr(listener_cog, 'wait_and_register_handlers'):
                BotLogger.info("CogLoader", f"重新註冊 {extension} 的訊息處理器...")
                bot.loop.create_task(listener_cog.wait_and_register_handlers())
        
        await ctx.send(f"✅ 重載: {extension}")
        BotLogger.command_used("cog.reload", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"重載: {extension}")
    except Exception as e:
        error_msg = f"重載 {extension} 失敗: {str(e)}"
        await ctx.send(f"❌ {error_msg}")
        BotLogger.error("CogLoader", error_msg, e)

@cog_group.command(name="reload_all", aliases=["rla"])
async def cog_reload_all(ctx):
    """重載所有 Cog 模組"""
    BotLogger.info("CogLoader", "🔄 開始重載所有 Cogs...")
    
    try:
        import os
        cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
        cog_files = [f[:-3] for f in os.listdir(cogs_dir) if f.endswith(".py")]
        
        reloaded = []
        failed = []
        
        for cog_name in cog_files:
            extension_name = f"cogs.{cog_name}"
            try:
                if extension_name in bot.extensions:
                    await bot.reload_extension(extension_name)
                    BotLogger.info("CogLoader", f"✅ 重載: {cog_name}")
                else:
                    await bot.load_extension(extension_name)
                    BotLogger.info("CogLoader", f"📥 載入: {cog_name}")
                reloaded.append(cog_name)
            except Exception as e:
                failed.append(f"{cog_name}: {e}")
                BotLogger.error("CogLoader", f"❌ {cog_name} 失敗: {e}")
        
        result = f"✅ 完成: 成功 {len(reloaded)}, 失敗 {len(failed)}"
        if failed:
            result += f"\n❌ 失敗列表: {', '.join([f.split(':')[0] for f in failed])}"
        
        await ctx.send(result)
        BotLogger.command_used("cog.reload_all", ctx.author.id, ctx.guild.id if ctx.guild else 0, result)
        
    except Exception as e:
        await ctx.send(f"❌ 重載失敗: {e}")
        BotLogger.error("CogLoader", f"重載所有 Cogs 錯誤: {e}")

# 向後相容的獨立指令
@bot.command(name="rl", help="reload cog (alias for ?cog reload)")
async def reload_compat(ctx, extension):
    """重載 Cog - 向後相容指令"""
    await cog_reload(ctx, extension)

@bot.command(name="rla", help="reload all cogs (alias for ?cog reload_all)")
async def reload_all_compat(ctx):
    """重載所有 Cogs - 向後相容指令"""
    await cog_reload_all(ctx)


# 移除重複的 debug_handlers 指令，改由 listener.py 提供


async def load_extensions():
    loaded_count = 0
    failed_count = 0
    
    # 使用絕對路徑避免部署環境路徑問題
    import os
    cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
    
    # 按字母順序載入 cogs 以便於除錯
    cog_files = sorted([f for f in os.listdir(cogs_dir) if f.endswith(".py")])
    BotLogger.info("CogLoader", f"準備載入 cogs: {[f[:-3] for f in cog_files]}")
    
    for filename in cog_files:
        cog_name = filename[:-3]
        BotLogger.info("CogLoader", f"正在載入: {cog_name}")
        try:
            await bot.load_extension(f"cogs.{cog_name}")
            BotLogger.info("CogLoader", f"成功載入: {cog_name}")
            loaded_count += 1
        except Exception as e:
            BotLogger.error("CogLoader", f"載入 {cog_name} 失敗", e)
            failed_count += 1
    
    BotLogger.warning(
        "CogLoader", 
        f"📦 Cog載入完成: 成功 {loaded_count}, 失敗 {failed_count}"
    )


async def main():
    # 先啟動 Flask keep_alive 服務，確保 Render 能檢測到開放端口
    if config.use_keep_alive:
        try:
            from keep_alive import keep_alive, set_bot_ready
            
            BotLogger.system_event("保持連線", "正在啟動 Flask 伺服器...")
            
            # 啟動並驗證 Flask 伺服器
            if keep_alive():
                BotLogger.system_event("保持連線", "Flask 伺服器啟動並驗證成功")
            else:
                BotLogger.error("KeepAlive", "Flask 伺服器啟動失敗，但繼續啟動機器人")
            
            # 額外等待時間，確保 Render 檢測到服務
            await asyncio.sleep(1)
            
        except ImportError as e:
            BotLogger.error("KeepAlive", "無法匯入 keep_alive 模組", e)
        except Exception as e:
            BotLogger.error("KeepAlive", "keep_alive 啟動過程發生錯誤", e)
    
    try:
        async with bot:
            BotLogger.system_event("開始載入擴充功能", "準備載入 cogs...")
            await load_extensions()
            
            # 更新機器人就緒狀態
            if config.use_keep_alive:
                try:
                    from keep_alive import set_bot_ready
                    set_bot_ready(True)
                except ImportError:
                    pass
            
            # 驗證 TOKEN 格式
            token_preview = f"{config.token[:10]}...{config.token[-10:]}" if config.token else "None"
            BotLogger.system_event("機器人啟動", f"正在連接到 Discord... (Token: {token_preview})")
            
            await bot.start(config.token)
            
    except discord.HTTPException as e:
        BotLogger.critical("BotMain", f"Discord HTTP 錯誤: {e.status} - {e.text}", e)
        # 更新狀態為失敗
        if config.use_keep_alive:
            try:
                from keep_alive import set_bot_ready
                set_bot_ready(False)
            except ImportError:
                pass
        raise
    except discord.LoginFailure as e:
        BotLogger.critical("BotMain", "Discord 登入失敗 - 檢查 TOKEN 是否正確", e)
        if config.use_keep_alive:
            try:
                from keep_alive import set_bot_ready
                set_bot_ready(False)
            except ImportError:
                pass
        raise
    except Exception as e:
        BotLogger.critical("BotMain", f"機器人啟動失敗: {type(e).__name__}", e)
        if config.use_keep_alive:
            try:
                from keep_alive import set_bot_ready
                set_bot_ready(False)
            except ImportError:
                pass
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        BotLogger.system_event("機器人關閉", "接收到中斷信號")
    except Exception as e:
        BotLogger.critical("BotMain", "機器人執行失敗", e)
        raise
