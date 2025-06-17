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

# 設定斜線指令同步
@bot.command(name="sync", help="同步斜線指令")
async def sync_commands(ctx: commands.Context, guild_id: str = None):
    """同步斜線指令到Discord
    
    Args:
        guild_id: 指定公會ID進行同步，留空則全域同步
    """
    try:
        if guild_id:
            # 公會特定同步（即時生效）
            try:
                guild_id_int = int(guild_id)
                guild = discord.Object(id=guild_id_int)
                bot.tree.copy_global_to(guild=guild)
                synced = await bot.tree.sync(guild=guild)
                await ctx.send(f"✅ 已同步 {len(synced)} 個斜線指令到公會 {guild_id}")
                BotLogger.command_used("sync", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"公會同步 {guild_id}: {len(synced)} 個指令")
            except ValueError:
                await ctx.send("❌ 公會ID必須是數字")
                return
        else:
            # 全域同步（需要等待Discord更新）
            synced = await bot.tree.sync()
            await ctx.send(f"✅ 已全域同步 {len(synced)} 個斜線指令（需等待Discord更新，約1小時）")
            BotLogger.command_used("sync", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"全域同步: {len(synced)} 個指令")
    except Exception as e:
        error_msg = f"同步指令失敗: {str(e)}"
        await ctx.send(error_msg)
        BotLogger.error("CommandSync", error_msg, e)

@bot.command(name="synchere", help="同步斜線指令到當前公會（即時生效）")
async def sync_here(ctx: commands.Context):
    """同步斜線指令到當前公會"""
    if not ctx.guild:
        await ctx.send("❌ 此指令只能在伺服器中使用")
        return
    
    try:
        guild = discord.Object(id=ctx.guild.id)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        await ctx.send(f"✅ 已同步 {len(synced)} 個斜線指令到當前伺服器（即時生效）")
        BotLogger.command_used("synchere", ctx.author.id, ctx.guild.id, f"即時同步: {len(synced)} 個指令")
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
