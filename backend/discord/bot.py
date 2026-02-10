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
    backend_dir = str(Path(__file__).resolve().parent.parent)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

# 載入 .env 環境變數 (必須在 import config 之前)
from dotenv import load_dotenv

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path, encoding="utf-8")

# 導入配置和 Discord 模組
import asyncpg  # noqa: E402
import discord  # noqa: E402
from discord.ext import commands  # noqa: E402

from core import COGS_DIR, BotConfig, HealthCheckServer, RateLimitMonitor  # noqa: E402
from shared.database import DatabaseManager, PoolConfig  # noqa: E402

try:
    from rich.console import Console
    from rich.logging import RichHandler

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


def setup_logging() -> None:
    """設定日誌系統"""
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)

    if RICH_AVAILABLE:
        try:
            # 設置 Windows UTF-8 輸出支援
            if sys.platform == "win32":
                import codecs

                sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer)
                sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer)

            console = Console(
                force_terminal=True,
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

    def __init__(self) -> None:
        # 設定 Intents (僅開啟必要的特權 Intents)
        intents = discord.Intents.default()
        intents.message_content = True  # Required for events.py message logging
        intents.members = True  # Required for moderation, utility, events, giveaway

        super().__init__(
            command_prefix=commands.when_mentioned_or("$"),
            intents=intents,
            help_command=None,  # 自訂 help 指令
        )

        self.initial_extensions: list[str] = self._get_extensions()
        self.rate_limiter = RateLimitMonitor(self)
        self._db_manager: DatabaseManager | None = None
        self.db_pool: asyncpg.Pool | None = None

    async def setup_database(self, max_retries: int = 5, retry_delay: float = 5.0) -> None:
        """Initialize the shared database connection pool."""
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable is not set")

        safe_url = database_url.split("@")[-1] if "@" in database_url else "invalid"
        logger.info(f"Connecting to database: {safe_url}")

        self._db_manager = DatabaseManager(
            database_url,
            PoolConfig(
                min_size=1,
                max_size=5,
                timeout=60.0,
                command_timeout=60.0,
                max_inactive_connection_lifetime=180.0,
                max_retries=max_retries,
                retry_delay=retry_delay,
                tcp_keepalives_idle=60,
                tcp_keepalives_interval=10,
                tcp_keepalives_count=5,
                health_check_interval=30,
            ),
        )
        await self._db_manager.connect()
        self.db_pool = self._db_manager.pool

    async def close_database(self) -> None:
        """Close the database connection pool."""
        if self._db_manager is not None:
            await self._db_manager.disconnect()
            self._db_manager = None
            self.db_pool = None

    def _get_extensions(self) -> list[str]:
        """動態掃描 cogs 目錄"""
        if not COGS_DIR.exists():
            return []

        return [
            f"cogs.{item.stem if item.is_file() else item.name}"
            for item in COGS_DIR.iterdir()
            if not item.name.startswith(("_", "."))
            and (
                (item.is_file() and item.suffix == ".py")
                or (item.is_dir() and (item / "__init__.py").exists())
            )
        ]

    async def setup_hook(self) -> None:
        """Bot 啟動時的初始化設置"""
        # 啟動速率限制監控
        await self.rate_limiter.start_monitoring()

        # 載入 Cogs
        loaded = []
        failed = []

        for extension in self.initial_extensions:
            try:
                await self.load_extension(extension)
                loaded.append(extension.split(".")[-1])
            except Exception as e:
                failed.append(f"{extension.split('.')[-1]} ({e})")

        # 顯示載入結果
        if loaded:
            cogs_list = ", ".join(loaded)
            if RICH_AVAILABLE:
                logger.info(f"[green]已載入 Cogs:[/green] {cogs_list}")
            else:
                logger.info(f"已載入 Cogs: {cogs_list}")

        if failed:
            failures = ", ".join(failed)
            if RICH_AVAILABLE:
                logger.error(f"[red]載入失敗:[/red] {failures}")
            else:
                logger.error(f"載入失敗: {failures}")

        # 同步斜線指令到 Discord（可透過環境變數控制）
        sync_commands = os.getenv("DISCORD_SYNC_COMMANDS", "true").lower() == "true"
        guild_id = os.getenv("DISCORD_GUILD_ID")

        if guild_id:
            self._sync_guild_id = guild_id

        if not sync_commands:
            if RICH_AVAILABLE:
                logger.info("[dim]跳過指令同步 (DISCORD_SYNC_COMMANDS=false)[/dim]")
            else:
                logger.info("跳過指令同步 (DISCORD_SYNC_COMMANDS=false)")
        else:
            try:
                if RICH_AVAILABLE:
                    logger.info("[yellow]正在同步斜線指令...[/yellow]")
                else:
                    logger.info("正在同步斜線指令...")

                if guild_id:
                    # 同步到測試伺服器 (更快)
                    guild = discord.Object(id=int(guild_id))
                    self.tree.copy_global_to(guild=guild)
                    synced = await self.tree.sync(guild=guild)

                    if RICH_AVAILABLE:
                        logger.info(f"[magenta]已同步 {len(synced)} 個指令到測試伺服器[/magenta]")
                    else:
                        logger.info(f"已同步 {len(synced)} 個指令到測試伺服器")
                else:
                    # 全域同步 (較慢,可能需要 1 小時生效)
                    synced = await self.tree.sync()
                    if RICH_AVAILABLE:
                        logger.info(f"[magenta]已全域同步 {len(synced)} 個指令[/magenta]")
                    else:
                        logger.info(f"已全域同步 {len(synced)} 個指令")

            except discord.HTTPException as e:
                if RICH_AVAILABLE:
                    logger.error(f"[red]指令同步失敗 (HTTP {e.status}):[/red] {e.text}")
                else:
                    logger.error(f"指令同步失敗 (HTTP {e.status}): {e.text}")
            except Exception as e:
                if RICH_AVAILABLE:
                    logger.error(f"[red]指令同步發生錯誤:[/red] {e}")
                else:
                    logger.error(f"指令同步發生錯誤: {e}")

        if RICH_AVAILABLE:
            logger.info("[yellow]正在連接 Discord...[/yellow]")
        else:
            logger.info("正在連接 Discord...")

    async def on_ready(self) -> None:
        """Bot 連接成功並就緒時觸發"""
        # 記錄同步的測試伺服器資訊
        if hasattr(self, "_sync_guild_id"):
            guild_obj = self.get_guild(int(self._sync_guild_id))
            if guild_obj:
                if RICH_AVAILABLE:
                    logger.info(
                        f"[cyan]測試伺服器:[/cyan] {guild_obj.name} (ID: {self._sync_guild_id})"
                    )
                else:
                    logger.info(f"測試伺服器: {guild_obj.name} (ID: {self._sync_guild_id})")

        # 取得並設定 Bot 擁有者 ID
        if not self.owner_id:
            app_info = await self.application_info()
            self.owner_id = app_info.owner.id
            # 優先使用 global_name（全局顯示名稱），否則使用 name（用戶名）
            owner_name = app_info.owner.global_name or app_info.owner.name
            if RICH_AVAILABLE:
                logger.info(f"[cyan]Bot Owner:[/cyan] {owner_name} (ID: {self.owner_id})")
            else:
                logger.info(f"Bot Owner: {owner_name} (ID: {self.owner_id})")

        # 應用配置的狀態和活動
        try:
            await self.change_presence(
                status=BotConfig.get_status(), activity=BotConfig.get_activity()
            )
        except Exception as e:
            logger.warning(f"Failed to set bot presence: {e}")

        # 記錄 Bot 資訊
        status = BotConfig.get_status()
        activity = BotConfig.get_activity()
        activity_str = f"{activity.name}" if activity else "無"

        if self.user is None:
            logger.error("Bot user is None")
            return

        if RICH_AVAILABLE:
            logger.info(
                f"[bold green]Bot 已就緒:[/bold green] {self.user} [dim](ID: {self.user.id})[/dim]"
            )
            logger.info(
                f"[cyan]連接資訊:[/cyan] {len(self.guilds)} 個伺服器 | discord.py {discord.__version__}"
            )
            logger.info(f"[cyan]Bot 狀態:[/cyan] {status.name} | {activity_str}")
        else:
            logger.info(f"Bot 已就緒: {self.user} (ID: {self.user.id})")
            logger.info(f"連接資訊: {len(self.guilds)} 個伺服器 | discord.py {discord.__version__}")
            logger.info(f"Bot 狀態: {status.name} | {activity_str}")

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
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


async def main() -> None:
    """Bot 啟動主函數 (具備自動重試與速率限制保護)"""
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        msg = "找不到 DISCORD_BOT_TOKEN 環境變數，請在 .env 中設定"
        logger.error(f"[bold red]{msg}[/bold red]" if RICH_AVAILABLE else msg)
        return

    http_port = int(os.getenv("PORT", "8080"))

    # 重試參數
    retry_count = 0
    max_retries = 5
    base_delay = 60  # 起始等待 60 秒

    async with NiibotClient() as bot:
        health_server = None
        try:
            # 啟動健康檢查伺服器
            health_server = HealthCheckServer(bot, port=http_port)
            await health_server.start()

            # 初始化資料庫連線池
            await bot.setup_database()

            while retry_count < max_retries:
                try:
                    await bot.start(token)
                    break  # 成功登入則跳出重試迴圈

                except discord.HTTPException as e:
                    # 429 Too Many Requests 或 Cloudflare 1015 錯誤
                    if e.status == 429:
                        retry_count += 1

                        # 解析詳細的速率限制資訊
                        scope = "unknown"
                        retry_after = base_delay * (2 ** (retry_count - 1))
                        is_cloudflare = False

                        # 檢查是否為 Cloudflare ban (1015)
                        if hasattr(e, "text") and e.text:
                            if "1015" in str(e.text) or "cloudflare" in str(e.text).lower():
                                is_cloudflare = True
                                logger.error(
                                    "[CLOUDFLARE BAN] 被 Cloudflare 暫時封鎖 (1015)，"
                                    "可能需要等待 24 小時或更換 IP"
                                )

                        # 嘗試從 response 取得 headers
                        if hasattr(e, "response") and e.response:
                            headers = getattr(e.response, "headers", {})
                            scope = headers.get("X-RateLimit-Scope", "unknown")
                            if "retry_after" in headers:
                                retry_after = float(headers.get("retry_after", retry_after))
                            elif "Retry-After" in headers:
                                retry_after = float(headers.get("Retry-After", retry_after))

                        # 計算等待時間 (使用 retry_after 或指數退避)
                        wait_time = max(retry_after, base_delay * (2 ** (retry_count - 1)))

                        # 詳細日誌
                        logger.warning(
                            f"[429 Rate Limit] scope={scope}, "
                            f"cloudflare={is_cloudflare}, "
                            f"retry_after={retry_after}s, "
                            f"wait={wait_time}s, "
                            f"attempt={retry_count}/{max_retries}"
                        )

                        await asyncio.sleep(wait_time)
                    else:
                        # 其他 HTTP 錯誤（如 401 Token 錯誤）不重試，直接拋出
                        raise
            else:
                # while 正常結束 = 重試次數已用完
                err_msg = f"已達最大重試次數 ({max_retries})，Bot 無法連線至 Discord。請稍後再試或檢查是否被 Cloudflare 暫時封鎖。"
                logger.error(f"[bold red]{err_msg}[/bold red]" if RICH_AVAILABLE else err_msg)

        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("接收到停止訊號...")
        except Exception as e:
            logger.error(f"Bot 運行期間發生嚴重錯誤: {e}", exc_info=True)
        finally:
            # 資源清理
            await bot.close_database()

            if health_server:
                await health_server.stop()

            if not bot.is_closed():
                await bot.close()

            logger.info("Bot 已安全關閉。")


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
