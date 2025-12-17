"""
Niibot Discord Bot
使用 discord.py 2.x 和 Slash Commands
"""

import asyncio
import logging
import os

from config import BotConfig
from discord.ext import commands
from dotenv import load_dotenv

import discord

try:
    from rich.console import Console
    from rich.logging import RichHandler

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# 載入環境變數
load_dotenv()


def setup_logging():
    """設定日誌系統"""
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)

    if RICH_AVAILABLE:
        try:
            console = Console(
                force_terminal=True,
                force_interactive=False,
                width=120,
            )

            rich_handler = RichHandler(
                console=console,
                show_time=True,
                show_level=True,
                show_path=False,
                markup=True,
                rich_tracebacks=True,
                tracebacks_show_locals=False,
                tracebacks_width=120,
            )

            rich_handler.setFormatter(
                logging.Formatter(fmt="%(message)s", datefmt="[%Y-%m-%d %H:%M:%S]")
            )

            logging.basicConfig(
                level=level,
                format="%(message)s",
                datefmt="[%Y-%m-%d %H:%M:%S]",
                handlers=[rich_handler],
            )

            logging.getLogger("discord").setLevel(logging.WARNING)
            logging.getLogger("discord.http").setLevel(logging.WARNING)

        except Exception as e:
            logging.basicConfig(
                level=level,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            logging.getLogger("discord_bot").warning(
                f"Failed to setup Rich logging: {e}, using standard logging"
            )
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


# 設定日誌
setup_logging()
logger = logging.getLogger("discord_bot")


class NiibotClient(commands.Bot):
    """Niibot Discord Bot 客戶端"""

    def __init__(self):
        # 設定 Intents
        intents = discord.Intents.default()
        intents.message_content = True  # 需要讀取訊息內容
        intents.members = True  # 需要讀取成員資訊
        intents.presences = True  # 需要讀取成員狀態

        super().__init__(
            command_prefix=commands.when_mentioned_or("$"),
            intents=intents,
            help_command=None,  # 自訂 help 指令
        )

        self.initial_extensions = [
            "cogs.utility",
            "cogs.moderation",
            "cogs.fun",
            "cogs.events",
        ]

    async def setup_hook(self):
        """Bot 啟動時的設置"""
        if RICH_AVAILABLE:
            logger.info("[bold yellow]開始載入 Cogs...[/bold yellow]")
        else:
            logger.info("開始載入 Cogs...")

        # 載入所有 Cogs
        for extension in self.initial_extensions:
            try:
                await self.load_extension(extension)
                if RICH_AVAILABLE:
                    logger.info(f"[green]✓[/green] {extension}")
                else:
                    logger.info(f"成功載入: {extension}")
            except Exception as e:
                if RICH_AVAILABLE:
                    logger.error(f"[red]✗[/red] {extension} - {e}")
                else:
                    logger.error(f"載入失敗: {extension} - {e}")

        # 同步斜線指令
        guild_id = os.getenv("DISCORD_GUILD_ID")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            if RICH_AVAILABLE:
                logger.info(f"[magenta]已同步斜線指令到測試伺服器[/magenta] (ID: {guild_id})")
            else:
                logger.info(f"已同步斜線指令到測試伺服器 (ID: {guild_id})")
        else:
            await self.tree.sync()
            if RICH_AVAILABLE:
                logger.info("[magenta]已全域同步斜線指令[/magenta]")
            else:
                logger.info("已全域同步斜線指令")

    async def on_ready(self):
        """Bot 就緒時觸發"""
        if RICH_AVAILABLE:
            logger.info("[bold green]Discord Bot 已就緒[/bold green]")
            logger.info(f"[cyan]Bot 名稱:[/cyan] {self.user}")
            logger.info(f"[cyan]Bot ID:[/cyan] {self.user.id}")
            logger.info(f"[cyan]discord.py 版本:[/cyan] {discord.__version__}")
            logger.info(f"[cyan]已連接伺服器:[/cyan] {len(self.guilds)} 個")
            logger.info(
                f"[cyan]狀態:[/cyan] {BotConfig.get_status().name} | "
                f"[cyan]活動:[/cyan] {BotConfig.get_activity()}"
            )
        else:
            logger.info("=" * 50)
            logger.info(f"Bot 已登入: {self.user} (ID: {self.user.id})")
            logger.info(f"discord.py 版本: {discord.__version__}")
            logger.info(f"已連接 {len(self.guilds)} 個伺服器")
            logger.info("=" * 50)

        # 設定 Bot 狀態
        await self.change_presence(
            status=BotConfig.get_status(), activity=BotConfig.get_activity()
        )

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """處理前綴指令錯誤"""
        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.MissingPermissions):
            await ctx.send("你沒有權限使用這個指令")
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"缺少必要參數: `{error.param.name}`")
            return

        logger.error(f"指令錯誤: {error}", exc_info=error)
        await ctx.send("執行指令時發生錯誤")


async def main():
    """主程式進入點"""
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        if RICH_AVAILABLE:
            logger.error("[bold red]找不到 DISCORD_BOT_TOKEN 環境變數[/bold red]")
            logger.error("請在 .env 文件中設定: DISCORD_BOT_TOKEN=your_token_here")
        else:
            logger.error("找不到 DISCORD_BOT_TOKEN 環境變數")
            logger.error("請在 .env 文件中設定: DISCORD_BOT_TOKEN=your_token_here")
        return

    async with NiibotClient() as bot:
        await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if RICH_AVAILABLE:
            logger.info("[yellow]Bot 已手動停止[/yellow]")
        else:
            logger.info("Bot 已手動停止")
    except Exception as e:
        if RICH_AVAILABLE:
            logger.error(f"[bold red]Bot 發生錯誤:[/bold red] {e}", exc_info=e)
        else:
            logger.error(f"Bot 發生錯誤: {e}", exc_info=e)
