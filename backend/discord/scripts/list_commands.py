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
logger = logging.getLogger("ListBot")

# 載入環境變數
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path, encoding="utf-8")

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")

if not TOKEN:
    logger.error("找不到 DISCORD_BOT_TOKEN，請檢查 .env 檔案")
    sys.exit(1)


class ListBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())

    async def setup_hook(self):
        print("-" * 40)
        print("Discord 指令查詢工具啟動")
        print("-" * 40)

        total = 0

        # 1. 全域指令查詢
        print("\n[1] 全域指令 (Global):")
        print("-" * 40)
        try:
            globals = await self.tree.fetch_commands()
            if globals:
                for i, cmd in enumerate(globals, 1):
                    print(f"  {i:2d}. /{cmd.name:15s} - {cmd.description}")
                total += len(globals)
            else:
                print("  (無全域指令)")
        except Exception as e:
            logger.error(f"查詢全域指令失敗: {e}")

        # 2. 伺服器指令查詢
        print(f"\n[2] 伺服器指令 (Guild ID: {GUILD_ID or '未設定'}):")
        print("-" * 40)
        if GUILD_ID:
            try:
                guild = discord.Object(id=int(GUILD_ID))
                guilds = await self.tree.fetch_commands(guild=guild)
                if guilds:
                    for i, cmd in enumerate(guilds, 1):
                        print(f"  {i:2d}. /{cmd.name:15s} - {cmd.description}")
                    total += len(guilds)
                else:
                    print("  (無伺服器專屬指令)")
            except Exception as e:
                logger.error(f"查詢伺服器指令失敗: {e}")
        else:
            print("  (跳過伺服器查詢，未設定 GUILD_ID)")

        print("\n" + "-" * 40)
        print(f"查詢完成: 總計 {total} 個指令")
        print("-" * 40)

        if total > 0:
            print("提示: 若有殘留指令，請執行 python clear_commands.py")

        await self.close()


async def main():
    bot = ListBot()
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n使用者取消執行")
