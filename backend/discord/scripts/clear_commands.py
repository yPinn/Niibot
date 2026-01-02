"""
Discord 指令清除工具

用途：清除 Discord 上所有註冊的舊指令
使用時機：當 Discord 上出現舊版本或重複指令時
執行方式：python clear_commands.py

注意：
- 這是一次性工具，執行完可保留供未來使用
- 清除後需重新啟動 bot.py 來同步新指令
- 會同時清除全域指令和測試伺服器指令
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

from discord.ext import commands
from dotenv import load_dotenv

import discord

# 設定簡單的日誌
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("clear_commands")

# 載入環境變數
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path, encoding="utf-8")

token = os.getenv("DISCORD_BOT_TOKEN")
guild_id = os.getenv("DISCORD_GUILD_ID")

if not token:
    logger.error("[ERROR] 找不到 DISCORD_BOT_TOKEN 環境變數")
    logger.error("        請檢查 .env 檔案")
    sys.exit(1)


class ClearBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        logger.info("=" * 60)
        logger.info("Discord 指令清除工具")
        logger.info("=" * 60)

        try:
            # 1. 清除全域指令
            logger.info("\n[Step 1/2] 清除全域指令...")
            self.tree.clear_commands(guild=None)
            global_synced = await self.tree.sync()
            logger.info(f"           SUCCESS - 全域指令已清除 (剩餘 {len(global_synced)} 個)")

            # 2. 清除測試伺服器指令
            if guild_id:
                logger.info(f"\n[Step 2/2] 清除測試伺服器指令 (Guild ID: {guild_id})...")
                guild = discord.Object(id=int(guild_id))
                self.tree.clear_commands(guild=guild)
                guild_synced = await self.tree.sync(guild=guild)
                logger.info(f"           SUCCESS - 測試伺服器指令已清除 (剩餘 {len(guild_synced)} 個)")
            else:
                logger.info("\n[Step 2/2] 跳過測試伺服器 (未設定 DISCORD_GUILD_ID)")

            logger.info("\n" + "=" * 60)
            logger.info("清除完成! Discord 上的所有指令已被移除")
            logger.info("=" * 60)
            logger.info("\n下一步: 執行 'python bot.py' 重新同步新指令")

        except discord.HTTPException as e:
            logger.error(f"\n[ERROR] HTTP 錯誤 ({e.status}): {e.text}")
        except Exception as e:
            logger.error(f"\n[ERROR] 發生錯誤: {e}")
        finally:
            # 關閉 bot
            await self.close()


async def main():
    async with ClearBot() as bot:
        await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n已取消")
