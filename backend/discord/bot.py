"""Niibot Discord Bot — discord.py 2.x with Slash Commands"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Ensure shared module is importable (backend/ directory)
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# Load .env before any config imports
from dotenv import load_dotenv  # noqa: E402

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path, encoding="utf-8")

import asyncpg  # noqa: E402
import discord  # noqa: E402
from discord.ext import commands  # noqa: E402

from core import (  # noqa: E402
    COGS_DIR,
    BotConfig,
    HealthCheckServer,
    RateLimitMonitor,
    setup_logging,
)
from shared.database import DatabaseManager, PoolConfig  # noqa: E402

setup_logging()
logger = logging.getLogger("discord_bot")


class NiibotClient(commands.Bot):
    """Niibot Discord Bot client"""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # Required for events.py message logging
        intents.members = True  # Required for moderation, utility, events, giveaway

        super().__init__(
            command_prefix=commands.when_mentioned_or("$"),
            intents=intents,
            help_command=None,
        )

        self.initial_extensions: list[str] = self._get_extensions()
        self.rate_limiter = RateLimitMonitor(self)
        self._db_manager: DatabaseManager | None = None
        self.db_pool: asyncpg.Pool | None = None
        self._commands_synced: bool = False
        self._heartbeat_task: asyncio.Task | None = None

    async def setup_database(self, max_retries: int = 5, retry_delay: float = 5.0) -> None:
        """Initialize database connection pool"""
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable is not set")

        safe_url = database_url.split("@")[-1] if "@" in database_url else "invalid"
        logger.info(f"Connecting to database: {safe_url}")

        self._db_manager = DatabaseManager(
            database_url,
            PoolConfig.for_service(
                "discord",
                max_retries=max_retries,
                retry_delay=retry_delay,
            ),
        )
        await self._db_manager.connect()
        self.db_pool = self._db_manager.pool
        self._heartbeat_task = asyncio.create_task(self._pool_heartbeat_loop())

    async def close_database(self) -> None:
        """Close the database connection pool."""
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        if self._db_manager is not None:
            await self._db_manager.disconnect()
            self._db_manager = None
            self.db_pool = None

    async def _pool_heartbeat_loop(self) -> None:
        """Periodically ping the DB pool to keep the idle connection alive.

        Constraint chain: heartbeat(15s) < max_inactive(45s) < Supavisor(~30-60s).
        """
        while True:
            await asyncio.sleep(15)
            try:
                if self.db_pool is not None:
                    async with self.db_pool.acquire(timeout=10.0) as conn:
                        await conn.fetchval("SELECT 1")
                    logger.debug("Pool heartbeat OK")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Pool heartbeat failed: {type(e).__name__}: {e}")

    def _get_extensions(self) -> list[str]:
        """Scan cogs directory for loadable extensions"""
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
        """Called when the bot is starting up"""
        await self.rate_limiter.start_monitoring()

        loaded = []
        failed = []

        for extension in self.initial_extensions:
            try:
                await self.load_extension(extension)
                loaded.append(extension.split(".")[-1])
            except Exception as e:
                failed.append(f"{extension.split('.')[-1]} ({e})")

        if loaded:
            logger.info(f"[green]Loaded cogs:[/green] {', '.join(loaded)}")
        if failed:
            logger.error(f"[red]Failed to load:[/red] {', '.join(failed)}")

        guild_id = os.getenv("DISCORD_GUILD_ID")
        if guild_id:
            self._sync_guild_id = guild_id

        # Command sync deferred to on_ready (avoid 429 during setup_hook)
        logger.info("[yellow]Connecting to Discord...[/yellow]")

    async def _sync_commands(self) -> None:
        """Sync slash commands (runs once after first on_ready)"""
        sync_commands = os.getenv("DISCORD_SYNC_COMMANDS", "true").lower() == "true"
        if not sync_commands:
            logger.info("Skipping command sync (DISCORD_SYNC_COMMANDS=false)")
            self._commands_synced = True
            return

        try:
            logger.info("Syncing slash commands...")
            guild_id = getattr(self, "_sync_guild_id", None)

            if guild_id:
                guild = discord.Object(id=int(guild_id))
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                logger.info(f"Synced {len(synced)} commands to test guild")
            else:
                synced = await self.tree.sync()
                logger.info(f"Synced {len(synced)} commands globally")

            self._commands_synced = True

        except discord.HTTPException as e:
            logger.error(f"Command sync failed (HTTP {e.status}): {e.text}")
            if e.status == 429:
                logger.warning("Command sync hit 429, will retry on next reconnect")
            else:
                self._commands_synced = True
        except Exception as e:
            logger.error(f"Command sync error: {e}")
            self._commands_synced = True

    async def on_ready(self) -> None:
        """Fired when the bot is connected and ready.

        All Discord API calls are wrapped in try/except to prevent 429
        responses from crashing the entire on_ready handler.
        """
        # Sync commands (first on_ready only, skip on reconnect)
        if not self._commands_synced:
            # Delay briefly after gateway connect to avoid immediate 429
            await asyncio.sleep(5)
            await self._sync_commands()

        if hasattr(self, "_sync_guild_id"):
            guild_obj = self.get_guild(int(self._sync_guild_id))
            if guild_obj:
                logger.info(
                    f"[cyan]Test guild:[/cyan] {guild_obj.name} (ID: {self._sync_guild_id})"
                )

        if not self.owner_id:
            try:
                app_info = await self.application_info()
                self.owner_id = app_info.owner.id
                owner_name = app_info.owner.global_name or app_info.owner.name
                logger.info(f"[cyan]Bot Owner:[/cyan] {owner_name} (ID: {self.owner_id})")
            except discord.HTTPException as e:
                logger.warning(f"Failed to fetch application_info (HTTP {e.status}): {e.text}")
            except Exception as e:
                logger.warning(f"Failed to fetch application_info: {e}")

        try:
            await self.change_presence(
                status=BotConfig.get_status(), activity=BotConfig.get_activity()
            )
        except Exception as e:
            logger.warning(f"Failed to set bot presence: {e}")

        status = BotConfig.get_status()
        activity = BotConfig.get_activity()
        activity_str = f"{activity.name}" if activity else "None"

        if self.user is None:
            logger.error("Bot user is None")
            return

        logger.info(
            f"[bold green]Bot ready:[/bold green] {self.user} [dim](ID: {self.user.id})[/dim]"
        )
        logger.info(
            f"[cyan]Connection:[/cyan] {len(self.guilds)} guilds | discord.py {discord.__version__}"
        )
        logger.info(f"[cyan]Status:[/cyan] {status.name} | {activity_str}")

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Handle prefix command errors"""
        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to use this command")
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing required argument: `{error.param.name}`")
            return

        logger.error(f"Command error: {error}", exc_info=error)
        await ctx.send("An error occurred while executing the command")


def _format_duration(seconds: float) -> str:
    """Format seconds into human-readable duration."""
    s = int(seconds)
    if s >= 3600:
        h, m = divmod(s, 3600)
        m //= 60
        return f"{h}h{m}m" if m else f"{h}h"
    if s >= 60:
        m, sec = divmod(s, 60)
        return f"{m}m{sec}s" if sec else f"{m}m"
    return f"{s}s"


def _parse_retry_after(e: discord.HTTPException, base_delay: float, attempt: int) -> float:
    """Extract retry_after from a 429 response (headers, JSON body, or fallback).

    Priority: discord.py parsed value > response headers > exponential backoff.
    For Cloudflare 1015 bans, enforces a minimum 20-minute wait.
    """
    retry_after: float | None = None

    # 1. discord.py may parse retry_after from JSON body into the exception
    if hasattr(e, "retry_after"):
        try:
            val = float(e.retry_after)
            if val > 0:
                retry_after = val
        except (ValueError, TypeError):
            pass

    # 2. Try response headers
    if retry_after is None:
        resp = getattr(e, "response", None)
        if resp:
            headers = getattr(resp, "headers", {})
            for key in ("Retry-After", "retry-after", "retry_after"):
                if key in headers:
                    try:
                        val = float(headers[key])
                        if val > 0:
                            retry_after = val
                    except (ValueError, TypeError):
                        pass
                    break

    # 3. Detect Cloudflare ban (1015) — enforce minimum 20 min wait
    text = getattr(e, "text", "") or ""
    is_cloudflare = "1015" in text or "cloudflare" in text.lower()

    if is_cloudflare:
        cf_min = 1200.0  # 20 minutes
        retry_after = max(retry_after or cf_min, cf_min)
        logger.error(
            f"[CLOUDFLARE BAN] Blocked by Cloudflare (1015). "
            f"Retry after {_format_duration(retry_after)}."
        )
    elif retry_after is None:
        # 4. Fallback: exponential backoff only when no retry_after provided
        retry_after = base_delay * (2 ** (attempt - 1))

    # 5. Log raw response body for debugging (non-Cloudflare only)
    if text and not is_cloudflare:
        logger.info(f"[429 Response] {text[:500]}")

    return retry_after


async def main() -> None:
    """Bot startup with auto-retry and rate limit protection"""
    # 1. Health server FIRST (Render needs a port quickly)
    health_server = HealthCheckServer()
    await health_server.start()

    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        logger.error("DISCORD_BOT_TOKEN not set")
        await health_server.stop()
        return

    retry_count = 0
    max_normal_retries = 5  # cap for normal 429s only
    base_delay = 60

    async with NiibotClient() as bot:
        health_server.bot = bot
        try:
            await bot.setup_database()

            while True:
                try:
                    await bot.start(token)
                    break

                except discord.HTTPException as e:
                    if e.status == 429:
                        text = getattr(e, "text", "") or ""
                        is_cloudflare = "1015" in text or "cloudflare" in text.lower()

                        # Cloudflare bans: always wait, never count toward retries
                        if not is_cloudflare:
                            retry_count += 1
                            if retry_count > max_normal_retries:
                                logger.error(
                                    f"Max retries reached ({max_normal_retries}). "
                                    f"Bot cannot connect to Discord."
                                )
                                break

                        wait_time = _parse_retry_after(e, base_delay, retry_count or 1)

                        logger.warning(
                            f"[429 {'CLOUDFLARE' if is_cloudflare else 'Rate Limit'}] "
                            f"waiting {_format_duration(wait_time)}"
                            + (
                                f", attempt={retry_count}/{max_normal_retries}"
                                if not is_cloudflare
                                else ""
                            )
                        )

                        # Close the internal HTTP session to prevent
                        # "Unclosed client session" warnings on retry
                        await bot.http.close()

                        await asyncio.sleep(wait_time)
                    else:
                        raise

        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Received stop signal...")
        except Exception as e:
            logger.error(f"Fatal error during bot runtime: {e}", exc_info=True)
        finally:
            await bot.close_database()
            await health_server.stop()
            if not bot.is_closed():
                await bot.close()
            logger.info("Bot shut down.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.warning("Shutting down due to KeyboardInterrupt...")
    except Exception as e:
        logger.critical(f"Fatal error: {type(e).__name__}: {e}")
        raise SystemExit(1) from None
