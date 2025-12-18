"""
Niibot Discord Bot
使用 discord.py 2.x 和 Slash Commands
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# 設置 Python 路徑 (直接執行時需要)
if __name__ == "__main__":
    backend_dir = Path(__file__).parent.parent
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

# 載入 .env 環境變數 (必須在 import config 之前)
from dotenv import load_dotenv

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path, encoding="utf-8")

# 導入配置和 Discord 模組
from config import BotConfig  # noqa: E402
from discord.ext import commands  # noqa: E402

import discord  # noqa: E402

try:
    from rich.console import Console
    from rich.logging import RichHandler

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


def setup_logging():
    """設定日誌系統"""
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)

    if RICH_AVAILABLE:
        try:
            # 設置 Windows UTF-8 輸出支援
            if sys.platform == "win32":
                import codecs

                sys.stdout = codecs.getwriter("utf-8")(
                    sys.stdout.buffer, errors="replace"
                )
                sys.stderr = codecs.getwriter("utf-8")(
                    sys.stderr.buffer, errors="replace"
                )

            # 配置 Rich Console
            console = Console(
                force_terminal=True,
                force_interactive=False,
                width=120,
                legacy_windows=False,
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

            # 降低 discord.py 的日誌等級
            logging.getLogger("discord").setLevel(logging.WARNING)
            logging.getLogger("discord.http").setLevel(logging.WARNING)

        except Exception as e:
            # Rich 設定失敗時使用標準日誌
            logging.basicConfig(
                level=level,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            logging.getLogger("discord_bot").warning(
                f"Rich logging setup failed: {e}, using standard logging"
            )
    else:
        # Rich 不可用時使用標準日誌
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
        """Bot 啟動時的初始化設置"""
        # 載入 Cogs
        if RICH_AVAILABLE:
            logger.info("[bold yellow]開始載入 Cogs...[/bold yellow]")
        else:
            logger.info("開始載入 Cogs...")

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

        # 同步斜線指令到 Discord
        if RICH_AVAILABLE:
            logger.info("[yellow]正在同步斜線指令...[/yellow]")
        else:
            logger.info("正在同步斜線指令...")

        guild_id = os.getenv("DISCORD_GUILD_ID")
        if guild_id:
            # 同步到測試伺服器 (更快)
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            if RICH_AVAILABLE:
                logger.info(
                    f"[magenta]已同步斜線指令到測試伺服器[/magenta] (ID: {guild_id})"
                )
            else:
                logger.info(f"已同步斜線指令到測試伺服器 (ID: {guild_id})")
        else:
            # 全域同步 (較慢,可能需要 1 小時生效)
            await self.tree.sync()
            if RICH_AVAILABLE:
                logger.info("[magenta]已全域同步斜線指令[/magenta]")
            else:
                logger.info("已全域同步斜線指令")

        if RICH_AVAILABLE:
            logger.info("[yellow]正在連接 Discord...[/yellow]")
        else:
            logger.info("正在連接 Discord...")

    async def on_ready(self):
        """Bot 連接成功並就緒時觸發"""
        # 應用配置的狀態和活動
        await self.change_presence(
            status=BotConfig.get_status(), activity=BotConfig.get_activity()
        )

        # 記錄 Bot 資訊
        if RICH_AVAILABLE:
            logger.info("[bold green]Discord Bot 已就緒[/bold green]")
            logger.info(f"[cyan]Bot 名稱:[/cyan] {self.user}")
            logger.info(f"[cyan]Bot ID:[/cyan] {self.user.id}")
            logger.info(f"[cyan]discord.py 版本:[/cyan] {discord.__version__}")
            logger.info(f"[cyan]已連接伺服器:[/cyan] {len(self.guilds)} 個")

            status = BotConfig.get_status()
            activity = BotConfig.get_activity()
            activity_str = f"{activity.name}" if activity else "無"
            logger.info(
                f"[cyan]狀態:[/cyan] {status.name} | [cyan]活動:[/cyan] {activity_str}"
            )
        else:
            logger.info("=" * 50)
            logger.info(f"Bot 已登入: {self.user} (ID: {self.user.id})")
            logger.info(f"discord.py 版本: {discord.__version__}")
            logger.info(f"已連接 {len(self.guilds)} 個伺服器")
            logger.info("=" * 50)

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
    """Bot 啟動主函數"""
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
        try:
            await bot.start(token)
        except (KeyboardInterrupt, asyncio.CancelledError):
            if not bot.is_closed():
                await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        if RICH_AVAILABLE:
            logger.info("[yellow]Bot 已手動停止[/yellow]")
        else:
            logger.info("Bot 已手動停止")
    except Exception as e:
        if RICH_AVAILABLE:
            logger.error(f"[bold red]Bot 發生錯誤:[/bold red] {e}", exc_info=e)
        else:
            logger.error(f"Bot 發生錯誤: {e}", exc_info=e)
