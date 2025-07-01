import asyncio
import os

import discord
from discord.ext import commands

from utils import util
from utils.util import create_activity, ensure_data_dir, get_deployment_info
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

# 設定斜線指令同步
@bot.command(name="sync", help="同步斜線指令")
async def sync_commands(ctx: commands.Context):
    """同步斜線指令 - 在伺服器中自動選擇伺服器同步，否則全域同步"""
    try:
        if ctx.guild:
            # 在伺服器中 - 執行伺服器同步（即時生效）
            if not _should_sync(ctx.guild.id):
                await ctx.send("⏱️ 此伺服器同步冷卻中，請稍後再試")
                return
            guild = discord.Object(id=ctx.guild.id)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            await ctx.send(f"✅ 已同步 {len(synced)} 個斜線指令到當前伺服器（即時生效）")
            BotLogger.command_used("sync", ctx.author.id, ctx.guild.id, f"公會同步: {len(synced)} 個指令")
        else:
            # 在私訊中 - 執行全域同步
            if not _should_sync():
                await ctx.send("⏱️ 全域同步冷卻中，請稍後再試")
                return
            synced = await bot.tree.sync()
            await ctx.send(f"✅ 已全域同步 {len(synced)} 個斜線指令（需等待Discord更新，約1小時）")
            BotLogger.command_used("sync", ctx.author.id, 0, f"全域同步: {len(synced)} 個指令")
                
    except Exception as e:
        error_msg = f"同步指令失敗: {str(e)}"
        await ctx.send(error_msg)
        BotLogger.error("CommandSync", error_msg, e)

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
            await ctx.send("❌ 公會ID必須是數字")
            return
    else:
        if not ctx.guild:
            await ctx.send("❌ 此指令只能在伺服器中使用，或提供公會ID")
            return
        guild = discord.Object(id=ctx.guild.id)
    
    try:
        bot.tree.clear_commands(guild=guild)
        await bot.tree.sync(guild=guild)
        await ctx.send(f"✅ 已清除公會 {guild.id} 的所有斜線指令")
        BotLogger.command_used("unsync", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"清除公會 {guild.id} 指令")
    except Exception as e:
        error_msg = f"清除指令失敗: {str(e)}"
        await ctx.send(error_msg)
        BotLogger.error("CommandSync", error_msg, e)

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
        await ctx.send(f"❌ 指令 `{command_name}` 目前被禁用\n原因: {reason}")
        BotLogger.info("CommandDisable", f"用戶 {ctx.author.id} 嘗試使用被禁用的指令: {command_name}")
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
    protected_commands = ["disable", "enable", "status"]
    if command_name in protected_commands:
        await ctx.send(f"❌ 無法禁用受保護的指令: `{command_name}`")
        return
    
    # 檢查指令是否存在
    command = bot.get_command(command_name)
    if not command:
        await ctx.send(f"❌ 找不到指令: `{command_name}`")
        return
    
    # 禁用指令
    _disabled_commands[command_name] = reason
    await _save_disabled_commands()
    await ctx.send(f"✅ 已禁用指令 `{command_name}`\n原因: {reason}")
    BotLogger.command_used("disable", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"禁用指令: {command_name}")

@bot.command(name="enable", help="啟用指令")
async def enable_command(ctx: commands.Context, command_name: str):
    """啟用指定指令
    
    Args:
        command_name: 要啟用的指令名稱
    """
    if command_name not in _disabled_commands:
        await ctx.send(f"ℹ️ 指令 `{command_name}` 並未被禁用")
        return
    
    # 啟用指令
    del _disabled_commands[command_name]
    await _save_disabled_commands()
    await ctx.send(f"✅ 已啟用指令 `{command_name}`")
    BotLogger.command_used("enable", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"啟用指令: {command_name}")

@bot.command(name="disabled", help="查看被禁用的指令")
async def list_disabled_commands(ctx: commands.Context):
    """查看當前被禁用的指令列表"""
    if not _disabled_commands:
        await ctx.send("✅ 目前沒有被禁用的指令")
        return
    
    embed = discord.Embed(
        title="🚫 被禁用的指令",
        color=discord.Color.red()
    )
    
    for cmd_name, reason in _disabled_commands.items():
        embed.add_field(
            name=f"`{cmd_name}`",
            value=reason,
            inline=False
        )
    
    await ctx.send(embed=embed)
    BotLogger.command_used("disabled", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"查看 {len(_disabled_commands)} 個禁用指令")

BotLogger.system_event("機器人初始化", f"環境: {ENV}, 前綴: {config.command_prefix}")


@bot.event
async def on_ready():
    BotLogger.warning("BotMain", f"🤖 機器人上線: {bot.user} (環境: {ENV})")
    
    try:
        activity = create_activity()
        await bot.change_presence(status=getattr(discord.Status, config.status), activity=activity)
        BotLogger.system_event("狀態設定", f"狀態: {config.status}, 活動: {config.activity_name}")
    except Exception as e:
        BotLogger.error("BotStatus", "設定機器人狀態失敗", e)
    
    # 載入禁用指令列表
    await _load_disabled_commands()

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


@bot.command(name="l", help="load")
async def load(ctx, extension):
    try:
        await bot.load_extension(f"cogs.{extension}")
        await ctx.send(f"L: {extension} done.")
        BotLogger.command_used("load", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"載入: {extension}")
    except Exception as e:
        error_msg = f"載入 {extension} 失敗: {str(e)}"
        await ctx.send(error_msg)
        BotLogger.error("CogLoader", error_msg, e)


@bot.command(name="u", help="unload")
async def unload(ctx, extension):
    try:
        await bot.unload_extension(f"cogs.{extension}")
        await ctx.send(f"U: {extension} done.")
        BotLogger.command_used("unload", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"卸載: {extension}")
    except Exception as e:
        error_msg = f"卸載 {extension} 失敗: {str(e)}"
        await ctx.send(error_msg)
        BotLogger.error("CogLoader", error_msg, e)

@bot.command(name="test")
async def test_command(ctx):
    """測試指令 - 顯示機器人狀態和部署信息"""
    BotLogger.info("TestCommand", f"測試指令執行 - 用戶: {ctx.author.id}")
    
    try:
        deployment_info = get_deployment_info()
        
        embed = discord.Embed(
            title="🤖 機器人測試",
            description="機器人運行正常",
            color=0x00ff00
        )
        
        embed.add_field(
            name="📍 部署信息",
            value=f"```{deployment_info}```",
            inline=False
        )
        
        embed.add_field(
            name="⚡ 狀態",
            value=f"延遲: {round(bot.latency * 1000)}ms\n伺服器數量: {len(bot.guilds)}",
            inline=True
        )
        
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text=f"請求者: {ctx.author.display_name}")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        BotLogger.error("TestCommand", "測試指令執行失敗", e)
        await ctx.send(f"✅ 測試完成（簡化模式）\n環境: {ENV}")


# 斜線指令版本的help
@bot.tree.command(name="help", description="顯示所有可用的斜線指令")
async def slash_help(interaction: discord.Interaction):
    """斜線指令版本的幫助指令"""
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
                            'description': command.description[:100] + '...' if len(command.description) > 100 else command.description
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
                        'description': command.description[:100] + '...' if len(command.description) > 100 else command.description
                    })
        
        if bot_commands:
            commands_by_cog['系統指令'] = bot_commands
        
        # 創建embed
        embed = discord.Embed(
            title="📚 Niibot 斜線指令列表",
            description="以下是所有可用的斜線指令：",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        # 按模組分組顯示指令
        for cog_name, commands in commands_by_cog.items():
            if commands:
                # 轉換cog名稱為中文
                cog_display_name = {
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
                }.get(cog_name, f"📦 {cog_name}")
                
                commands_text = []
                for cmd in commands[:5]:  # 限制每個分類最多5個指令，避免embed過長
                    commands_text.append(f"`/{cmd['name']}` - {cmd['description']}")
                
                if len(commands) > 5:
                    commands_text.append(f"... 還有 {len(commands) - 5} 個指令")
                
                embed.add_field(
                    name=cog_display_name,
                    value="\n".join(commands_text) if commands_text else "無可用指令",
                    inline=False
                )
        
        # 添加傳統指令提示
        embed.add_field(
            name="💡 提示",
            value="• 斜線指令以 `/` 開頭\n• 傳統指令以 `?` 開頭\n• 使用 `?help` 查看傳統指令列表",
            inline=False
        )
        
        embed.set_footer(
            text="Niibot",
            icon_url=bot.user.display_avatar.url if bot.user else None
        )
        
        await interaction.response.send_message(embed=embed)
        
        # 記錄指令使用
        BotLogger.command_used(
            "help",
            interaction.user.id,
            interaction.guild.id if interaction.guild else 0,
            f"查看斜線指令列表，共 {sum(len(cmds) for cmds in commands_by_cog.values())} 個指令"
        )
        
    except Exception as e:
        BotLogger.error("SlashHelp", f"斜線help指令執行失敗", e)
        await interaction.response.send_message(
            "❌ 獲取指令列表時發生錯誤，請稍後再試",
            ephemeral=True
        )


@bot.command(name="rl", help="reload")
async def reload(ctx, extension):
    try:
        await bot.reload_extension(f"cogs.{extension}")
        
        # 如果重載的不是 listener，且 listener 已載入，則重新觸發處理器註冊
        if extension != "listener" and "cogs.listener" in bot.extensions:
            listener_cog = bot.get_cog("Listener")
            if listener_cog and hasattr(listener_cog, 'wait_and_register_handlers'):
                BotLogger.info("CogLoader", f"重新註冊 {extension} 的訊息處理器...")
                bot.loop.create_task(listener_cog.wait_and_register_handlers())
        
        await ctx.send(f"RL: {extension} done.")
        BotLogger.command_used("reload", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"重載: {extension}")
    except Exception as e:
        error_msg = f"重載 {extension} 失敗: {str(e)}"
        await ctx.send(error_msg)
        BotLogger.error("CogLoader", error_msg, e)


@bot.command(name="rla", help="reload all")
async def reload_all(ctx):
    """最簡單的重載所有cog"""
    BotLogger.info("CogLoader", "🔄 開始簡單重載...")
    
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
        
        result = f"✅ 完成: 成功{len(reloaded)}, 失敗{len(failed)}"
        await ctx.send(result)
        BotLogger.command_used("rla", ctx.author.id, ctx.guild.id if ctx.guild else 0, result)
        
    except Exception as e:
        await ctx.send(f"❌ 重載失敗: {e}")
        BotLogger.error("CogLoader", f"rla錯誤: {e}")


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
            
            BotLogger.system_event("機器人啟動", "正在連接到 Discord...")
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
