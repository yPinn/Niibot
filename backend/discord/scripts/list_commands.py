"""
Discord 指令查詢工具

用途：查詢 Discord 上目前註冊的所有指令
使用時機：檢查是否有舊指令殘留，或驗證同步結果
執行方式：python list_commands.py

注意：
- 這是唯讀工具，不會修改任何指令
- 會分別列出全域指令和測試伺服器指令
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
logger = logging.getLogger("list_commands")

# 載入環境變數
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path, encoding="utf-8")

_token = os.getenv("DISCORD_BOT_TOKEN")
guild_id = os.getenv("DISCORD_GUILD_ID")

if not _token:
    logger.error("[ERROR] 找不到 DISCORD_BOT_TOKEN 環境變數")
    logger.error("        請檢查 .env 檔案")
    sys.exit(1)

# Type narrowing for mypy
token: str = _token


class ListBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        logger.info("=" * 60)
        logger.info("Discord 指令查詢工具")
        logger.info("=" * 60)

        total_commands = 0

        # 1. 查詢全域指令
        logger.info("\n[1] 全域指令 (所有伺服器):")
        logger.info("-" * 60)
        try:
            global_commands = await self.tree.fetch_commands()
            if global_commands:
                for i, cmd in enumerate(global_commands, 1):
                    logger.info(f"  {i:2d}. /{cmd.name:20s} - {cmd.description}")
                logger.info(f"\n  總計: {len(global_commands)} 個")
                total_commands += len(global_commands)
            else:
                logger.info("  (無全域指令)")
        except Exception as e:
            logger.error(f"  [ERROR] {e}")

        # 2. 查詢測試伺服器指令
        if guild_id:
            logger.info(f"\n[2] 測試伺服器指令 (Guild ID: {guild_id}):")
            logger.info("-" * 60)
            try:
                guild = discord.Object(id=int(guild_id))
                guild_commands = await self.tree.fetch_commands(guild=guild)
                if guild_commands:
                    for i, cmd in enumerate(guild_commands, 1):
                        logger.info(f"  {i:2d}. /{cmd.name:20s} - {cmd.description}")
                    logger.info(f"\n  總計: {len(guild_commands)} 個")
                    total_commands += len(guild_commands)
                else:
                    logger.info("  (無測試伺服器指令)")
            except Exception as e:
                logger.error(f"  [ERROR] {e}")
        else:
            logger.info("\n[2] 測試伺服器指令:")
            logger.info("-" * 60)
            logger.info("  (未設定 DISCORD_GUILD_ID)")

        logger.info("\n" + "=" * 60)
        logger.info(f"查詢完成 - Discord 上共有 {total_commands} 個指令")
        logger.info("=" * 60)

        # 提示
        if total_commands > 0:
            logger.info("\n提示: 如發現舊指令，執行 'python clear_commands.py' 清除")
        else:
            logger.info("\n提示: 目前無任何指令，執行 'python bot.py' 同步新指令")

        # 關閉 bot
        await self.close()


async def main():
    async with ListBot() as bot:
        await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n已取消")
