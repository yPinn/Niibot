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
from ui.help_system import HelpPaginationView
from core.command_manager import setup_command_manager
from core.sync_manager import setup_sync_manager

ENV = config.get('BOT_ENV', 'local')

# 初始化日誌系統
BotLogger.initialize(config.log_level, config.log_file)

# 確保資料目錄存在
ensure_data_dir()

# keep_alive 將在 main() 函數中啟動

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=config.command_prefix, intents=intents)

# 設置指令管理器和同步管理器
command_manager = setup_command_manager(bot)
sync_manager = setup_sync_manager(bot)

# 機器人啟動時間記錄
startup_time = None

# 同步指令系統已移至 core/sync_manager.py

# 指令禁用系統已移至 core/command_manager.py

# 指令禁用功能的 disable, enable, disabled 指令已移至 core/command_manager.py

BotLogger.system_event("機器人初始化", f"環境: {ENV}, 前綴: {config.command_prefix}")


@bot.event
async def on_ready():
    global startup_time
    startup_time = datetime.now(datetime.UTC)
    bot._startup_time = startup_time  # 供 cogs 使用

    BotLogger.system_event("機器人就緒", f"🤖 {bot.user} 已上線 (環境: {ENV})")


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


# Cog 管理指令已移至 cogs/admin_commands.py
# 系統狀態指令已移至 cogs/system_commands.py
# Help 系統保留在此以保持斜線指令可用性

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


async def load_extensions():
    loaded_count = 0
    failed_count = 0
    loaded_cogs = []
    failed_cogs = []

    # 使用絕對路徑避免部署環境路徑問題
    import os
    cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")

    # 按字母順序載入 cogs 以便於除錯
    cog_files = sorted([f for f in os.listdir(cogs_dir) if f.endswith(".py")])
    
    BotLogger.system_event("Cog載入", f"開始載入 {len(cog_files)} 個模組...")

    for filename in cog_files:
        cog_name = filename[:-3]
        try:
            await bot.load_extension(f"cogs.{cog_name}")
            loaded_cogs.append(cog_name)
            loaded_count += 1
        except Exception as e:
            BotLogger.error("CogLoader", f"載入 {cog_name} 失敗", e)
            failed_cogs.append(cog_name)
            failed_count += 1

    # 總結載入結果
    if loaded_count > 0:
        BotLogger.system_event("Cog載入", f"✅ 成功載入 {loaded_count} 個模組: {', '.join(loaded_cogs)}")
    
    if failed_count > 0:
        BotLogger.error("CogLoader", f"❌ 載入失敗 {failed_count} 個模組: {', '.join(failed_cogs)}")
    else:
        BotLogger.system_event("Cog載入", "🎉 所有模組載入成功！")


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
            BotLogger.system_event(
                "機器人啟動", f"正在連接到 Discord... (Token: {token_preview})")

            await bot.start(config.token)

    except discord.HTTPException as e:
        BotLogger.critical(
            "BotMain", f"Discord HTTP 錯誤: {e.status} - {e.text}", e)
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
