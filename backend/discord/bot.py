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

from shared.config_base import load_dev_env  # noqa: E402

load_dev_env("discord")

import asyncpg  # noqa: E402
import discord  # noqa: E402
from discord.ext import commands  # noqa: E402

from core import (  # noqa: E402
    COGS_DIR,
    BotConfig,
    HealthCheckServer,
    RateLimitMonitor,
    close_session,
    get_settings,
    setup_logging,
)
from shared.database import DatabaseManager, PoolConfig, pool_heartbeat_loop  # noqa: E402
from shared.log_context import bound_log_context  # noqa: E402
from shared.retry_utils import format_duration as _format_duration  # noqa: E402
from shared.retry_utils import parse_retry_after as _parse_retry_after_shared  # noqa: E402

LOGGER: logging.Logger = logging.getLogger(__name__)


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
        database_url = get_settings().database_url
        safe_url = database_url.split("@")[-1] if "@" in database_url else "invalid"
        LOGGER.info(f"Connecting to database: {safe_url}")

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
        self._heartbeat_task = asyncio.create_task(pool_heartbeat_loop(self._db_manager))

    async def close_database(self) -> None:
        """Close the database connection pool."""
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        if self._db_manager is not None:
            await self._db_manager.disconnect()
            self._db_manager = None
            self.db_pool = None

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
            LOGGER.info(f"Loaded cogs: {', '.join(loaded)}")
        if failed:
            LOGGER.error(f"Failed to load cogs: {', '.join(failed)}")

        @self.tree.error
        async def on_app_command_error(
            interaction: discord.Interaction,
            error: discord.app_commands.AppCommandError,
        ) -> None:
            cmd = interaction.command.qualified_name if interaction.command else None
            with bound_log_context(
                command=cmd,
                guild_id=interaction.guild_id,
                channel_id=interaction.channel_id,
            ):
                if isinstance(error, discord.app_commands.MissingPermissions):
                    msg = "你沒有使用此指令的權限"
                elif isinstance(error, discord.app_commands.CheckFailure):
                    msg = "權限不足"
                else:
                    LOGGER.error("Unhandled app command error", exc_info=error)
                    msg = "指令執行時發生錯誤"
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(msg, ephemeral=True)
                else:
                    await interaction.followup.send(msg, ephemeral=True)
            except Exception:
                pass

        guild_id = os.getenv("DISCORD_GUILD_ID")
        if guild_id:
            self._sync_guild_id = guild_id

        LOGGER.info("Connecting to Discord...")

    async def _sync_commands(self) -> None:
        """Sync slash commands (runs once after first on_ready)"""
        sync_commands = os.getenv("DISCORD_SYNC_COMMANDS", "false").lower() == "true"
        if not sync_commands:
            LOGGER.info("Skipping command sync (DISCORD_SYNC_COMMANDS=false)")
            self._commands_synced = True
            return

        try:
            LOGGER.info("Syncing slash commands...")
            guild_id = getattr(self, "_sync_guild_id", None)

            if guild_id:
                guild = discord.Object(id=int(guild_id))
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                LOGGER.info(f"Synced {len(synced)} commands to test guild")
            else:
                synced = await self.tree.sync()
                LOGGER.info(f"Synced {len(synced)} commands globally")

            self._commands_synced = True

        except discord.HTTPException as e:
            LOGGER.error(f"Command sync failed (HTTP {e.status}): {e.text}")
            if e.status == 429:
                LOGGER.warning("Command sync hit 429, will retry on next reconnect")
            else:
                self._commands_synced = True
        except Exception as e:
            LOGGER.error(f"Command sync error: {e}")
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
                LOGGER.info(f"Test guild: {guild_obj.name} (ID: {self._sync_guild_id})")

        if not self.owner_id:
            try:
                app_info = await self.application_info()
                self.owner_id = app_info.owner.id
                owner_name = app_info.owner.global_name or app_info.owner.name
                LOGGER.info(f"Bot owner: {owner_name} (ID: {self.owner_id})")
            except discord.HTTPException as e:
                LOGGER.warning(f"Failed to fetch application_info (HTTP {e.status}): {e.text}")
            except Exception as e:
                LOGGER.warning(f"Failed to fetch application_info: {e}")

        status = BotConfig.get_status()
        activity = BotConfig.get_activity()
        try:
            await self.change_presence(status=status, activity=activity)
        except Exception as e:
            LOGGER.warning(f"Failed to set bot presence: {e}")

        description = get_settings().discord_description
        if description:
            try:
                await self.http.edit_application_info(
                    reason=None, payload={"description": description[:400]}
                )
                LOGGER.info(
                    f"Bot description set: {description[:40]}{'...' if len(description) > 40 else ''}"
                )
            except Exception as e:
                LOGGER.warning(f"Failed to set bot description: {e}")
        else:
            LOGGER.debug("DISCORD_DESCRIPTION not set, skipping description update")

        if self.user is None:
            LOGGER.error("Bot user is None")
            return

        activity_str = f"{activity.name}" if activity else "None"
        LOGGER.info(
            f"Bot ready: {self.user} (ID: {self.user.id}) | "
            f"{len(self.guilds)} guilds | {status.name} | {activity_str}"
        )

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

        with bound_log_context(
            command=ctx.command.qualified_name if ctx.command else None,
            guild_id=ctx.guild.id if ctx.guild else None,
            channel_id=ctx.channel.id if ctx.channel else None,
        ):
            LOGGER.error(f"Command error: {error}", exc_info=error)
        await ctx.send("An error occurred while executing the command")


def _is_cloudflare_error(e: discord.HTTPException) -> bool:
    text = getattr(e, "text", "") or ""
    return "1015" in text or "cloudflare" in text.lower()


def _parse_retry_after(e: discord.HTTPException, base_delay: float, attempt: int) -> float:
    """Extract retry_after from a 429 response.

    Uses shared parse_retry_after for generic extraction, then applies
    Discord-specific Cloudflare 1015 ban handling (minimum 20-minute wait).
    """
    fallback = base_delay * (2 ** (attempt - 1))
    retry_after = _parse_retry_after_shared(e, fallback=fallback)

    # Detect Cloudflare ban (1015) — enforce minimum 20 min wait
    is_cloudflare = _is_cloudflare_error(e)
    if is_cloudflare:
        cf_min = 1200.0  # 20 minutes
        retry_after = max(retry_after, cf_min)
        LOGGER.error(f"Cloudflare ban (1015). Retry after {_format_duration(retry_after)}.")
    else:
        text = getattr(e, "text", "") or ""
        if text:
            LOGGER.info(f"Rate limit 429 response body: {text[:500]}")

    return retry_after


async def main() -> None:
    """Bot startup with auto-retry and rate limit protection"""
    try:
        setup_logging(get_settings())
    except Exception as exc:
        print(f"FATAL: Environment configuration error:\n  {exc}", file=sys.stderr)
        raise SystemExit(1) from None

    # 1. Health server FIRST (bind port before heavy setup)
    health_server = HealthCheckServer()
    await health_server.start()

    token = get_settings().discord_bot_token

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
                        is_cloudflare = _is_cloudflare_error(e)

                        # Cloudflare bans: always wait, never count toward retries
                        if not is_cloudflare:
                            retry_count += 1
                            if retry_count > max_normal_retries:
                                LOGGER.error(
                                    f"Max retries reached ({max_normal_retries}). "
                                    f"Bot cannot connect to Discord."
                                )
                                break

                        wait_time = _parse_retry_after(e, base_delay, retry_count or 1)

                        LOGGER.warning(
                            f"{'Cloudflare' if is_cloudflare else 'Rate limit'} 429, "
                            f"waiting {_format_duration(wait_time)}"
                            + (
                                f" | attempt={retry_count}/{max_normal_retries}"
                                if not is_cloudflare
                                else ""
                            )
                        )

                        # Close leaked HTTP session before retry
                        try:
                            s = getattr(bot.http, "_HTTPClient__session", None)
                            if s and not s.closed:
                                await s.close()
                        except Exception:
                            pass

                        await asyncio.sleep(wait_time)
                    else:
                        raise

        except (KeyboardInterrupt, asyncio.CancelledError):
            LOGGER.info("Received stop signal...")
        except Exception as e:
            LOGGER.error(f"Fatal error during bot runtime: {e}", exc_info=True)
        finally:
            await bot.close_database()
            await close_session()
            await health_server.stop()
            if not bot.is_closed():
                await bot.close()
            LOGGER.info("Bot shut down.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        LOGGER.warning("Shutting down due to KeyboardInterrupt...")
    except Exception as e:
        LOGGER.critical(f"Fatal error: {type(e).__name__}: {e}")
        raise SystemExit(1) from None
