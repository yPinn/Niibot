import asyncio
import os

import discord
from discord.ext import commands

from utils import util
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

@bot.command(name="test")
async def test_command(ctx):
    """極簡測試指令"""
    import traceback
    import time
    import asyncio
    
    # 獲取當前任務和事件循環資訊
    current_task = asyncio.current_task()
    loop = asyncio.get_event_loop()
    
    stack_trace = ''.join(traceback.format_stack()[-5:])  # 更多堆疊資訊
    timestamp = time.time()
    
    BotLogger.info("TestCommand", f"🧪 測試指令被執行 - 用戶: {ctx.author.id}")
    BotLogger.info("TestCommand", f"⏰ 時間戳: {timestamp}")
    BotLogger.info("TestCommand", f"🔄 當前任務: {current_task.get_name() if current_task else 'None'}")
    BotLogger.info("TestCommand", f"📍 完整調用堆疊:\n{stack_trace}")
    
    # 檢查是否有其他相同的任務在運行
    all_tasks = asyncio.all_tasks()
    test_tasks = [task for task in all_tasks if 'test' in str(task).lower()]
    BotLogger.info("TestCommand", f"🔍 相關任務數量: {len(test_tasks)}")
    
    await ctx.send("✅ 測試指令執行完成")


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
    
    BotLogger.system_event(
        "Cog載入完成", 
        f"成功: {loaded_count}, 失敗: {failed_count}"
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
            BotLogger.info("TokenDebug", f"Token 長度: {len(config.token)} 字符")
            BotLogger.info("TokenDebug", f"Token 開頭: {config.token[:20]}...")
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
