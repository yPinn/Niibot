import asyncio
import os

import discord
from discord.ext import commands

from utils.util import create_activity, ensure_data_dir
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

BotLogger.system_event("機器人初始化", f"環境: {ENV}, 前綴: {config.command_prefix}")


@bot.event
async def on_ready():
    BotLogger.system_event("機器人上線", f"使用者: {bot.user}, 環境: {ENV}")
    
    try:
        activity = create_activity()
        await bot.change_presence(status=getattr(discord.Status, config.status), activity=activity)
        BotLogger.system_event("狀態設定", f"狀態: {config.status}, 活動: {config.activity_name}")
    except Exception as e:
        BotLogger.error("BotStatus", "設定機器人狀態失敗", e)


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


@bot.command(name="rl", help="reload")
async def reload(ctx, extension):
    try:
        await bot.reload_extension(f"cogs.{extension}")
        await ctx.send(f"RL: {extension} done.")
        BotLogger.command_used("reload", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"重載: {extension}")
    except Exception as e:
        error_msg = f"重載 {extension} 失敗: {str(e)}"
        await ctx.send(error_msg)
        BotLogger.error("CogLoader", error_msg, e)


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
    
    BotLogger.system_event(
        "Cog載入完成", 
        f"成功: {loaded_count}, 失敗: {failed_count}"
    )


async def main():
    # 先啟動 Flask keep_alive 服務，讓 Render 檢測到開放端口
    if config.use_keep_alive:
        try:
            from keep_alive import keep_alive
            keep_alive()
            BotLogger.system_event("保持連線", "Flask 伺服器已啟動")
            # 給 Flask 時間完全啟動並讓 Render 檢測到
            import asyncio
            await asyncio.sleep(2)
        except ImportError as e:
            BotLogger.error("KeepAlive", "無法匯入 keep_alive 模組", e)
    
    try:
        async with bot:
            BotLogger.system_event("開始載入擴充功能", "準備載入 cogs...")
            await load_extensions()
            BotLogger.system_event("機器人啟動", "正在連接到 Discord...")
            BotLogger.info("TokenDebug", f"Token 長度: {len(config.token)} 字符")
            BotLogger.info("TokenDebug", f"Token 開頭: {config.token[:20]}...")
            await bot.start(config.token)
    except discord.HTTPException as e:
        BotLogger.critical("BotMain", f"Discord HTTP 錯誤: {e.status} - {e.text}", e)
        raise
    except discord.LoginFailure as e:
        BotLogger.critical("BotMain", "Discord 登入失敗 - 檢查 TOKEN 是否正確", e)
        raise
    except Exception as e:
        BotLogger.critical("BotMain", f"機器人啟動失敗: {type(e).__name__}", e)
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        BotLogger.system_event("機器人關閉", "接收到中斷信號")
    except Exception as e:
        BotLogger.critical("BotMain", "機器人執行失敗", e)
        raise
