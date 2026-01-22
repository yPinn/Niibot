import asyncio
import logging
import os
import sys
from pathlib import Path

from discord.ext import commands
from dotenv import load_dotenv

import discord

# 設定日誌格式
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("ClearBot")

# 載入環境變數
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path, encoding="utf-8")

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")

if not TOKEN:
    logger.error("找不到 DISCORD_BOT_TOKEN，請檢查 .env 檔案")
    sys.exit(1)


class ClearBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())

    async def setup_hook(self):
        print("-" * 40)
        print("Discord 指令清除工具啟動")
        print("-" * 40)

        try:
            # 1. 清除全域指令
            logger.info("正在清除全域指令...")
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
            logger.info("全域指令清除完成")

            # 2. 清除特定伺服器指令
            if GUILD_ID:
                logger.info(f"正在清除特定伺服器指令 (ID: {GUILD_ID})...")
                guild = discord.Object(id=int(GUILD_ID))
                self.tree.clear_commands(guild=guild)
                await self.tree.sync(guild=guild)
                logger.info("特定伺服器指令清除完成")

            print("-" * 40)
            print("清除作業結束")
            print("請重新執行 'python bot.py' 以同步新指令")
            print("-" * 40)

        except discord.Forbidden:
            logger.error("Bot 權限不足，請確認是否擁有 'applications.commands' 權限")
        except Exception as e:
            logger.error(f"執行過程中發生錯誤: {e}")
        finally:
            await self.close()


async def main():
    bot = ClearBot()
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n使用者取消執行")
