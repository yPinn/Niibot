"""Twitch bot launcher — entry point only."""

import asyncio
import logging
import sys
from pathlib import Path

# Ensure shared module is importable (backend/ directory)
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

LOGGER: logging.Logger = logging.getLogger(__name__)


def main() -> None:
    # Load .env files into OS env for os.getenv() call sites.
    # Order mirrors docker-compose.yml: shared.env first, then service-specific .env.
    from dotenv import load_dotenv

    _twitch_dir = Path(__file__).parent
    load_dotenv(dotenv_path=_twitch_dir.parent / "shared.env")
    load_dotenv(dotenv_path=_twitch_dir.parent / "shared.env.local", override=True)
    load_dotenv(dotenv_path=_twitch_dir / ".env", override=True)

    # Minimal imports for health server — bind port before heavy setup
    from core.config import get_settings
    from core.health_server import HealthCheckServer
    from core.logging_setup import setup_logging

    try:
        setup_logging(get_settings())
    except Exception as exc:
        import sys as _sys

        print(f"FATAL: Environment configuration error:\n  {exc}", file=_sys.stderr)
        raise SystemExit(1) from None

    async def runner() -> None:
        # 1. Health server FIRST (bind port before heavy setup)
        health_server = HealthCheckServer()
        await health_server.start()

        # 2. Heavy imports — after port is open
        from twitchio import eventsub

        from core import get_channel_subscriptions
        from core.bot import Bot
        from core.config import get_settings
        from shared.database import DatabaseManager, PoolConfig
        from shared.repositories.channel import ChannelRepository
        from shared.retry_utils import format_duration, parse_retry_after

        settings = get_settings()

        client_id: str = settings.twitch_client_id
        client_secret: str = settings.twitch_client_secret
        bot_id: str = settings.bot_id
        owner_id: str = settings.owner_id
        database_url: str = settings.database_url
        conduit_id: str | None = settings.conduit_id or None

        # 3. Database connection pool
        db_manager = DatabaseManager(
            database_url,
            PoolConfig.for_service("twitch"),
        )
        await db_manager.connect()
        pool = db_manager.pool

        try:
            subs: list[eventsub.SubscriptionPayload] = []
            channel_repo = ChannelRepository(pool)

            # 4. Retry DB query (cross-region timeout)
            for attempt in range(1, 6):
                try:
                    enabled_channels = await channel_repo.list_enabled_channels()
                    for ch in enabled_channels:
                        if ch.channel_id == bot_id:
                            continue
                        subs.extend(get_channel_subscriptions(ch.channel_id, bot_id))
                    break
                except (TimeoutError, OSError) as e:
                    LOGGER.warning(f"Database connect attempt ({attempt}/5): {type(e).__name__}")
                    if attempt < 5:
                        await asyncio.sleep(5)

            if subs:
                LOGGER.info(f"Starting bot with {len(subs)} initial subscriptions")
            else:
                LOGGER.error(
                    "Starting bot without initial subscriptions — bot is deaf to all channel events until background retry succeeds"
                )

            # 5. Start bot with auto-retry on rate limit
            retry_count = 0
            max_retries = 5
            base_delay = 60

            async with Bot(
                client_id=client_id,
                client_secret=client_secret,
                bot_id=bot_id,
                owner_id=owner_id,
                conduit_id=conduit_id,
                token_database=pool,
                db_manager=db_manager,
                database_url=database_url,
                subs=subs,
            ) as bot:
                health_server.bot = bot

                while retry_count < max_retries:
                    try:
                        await bot.start()
                        break
                    except Exception as e:
                        status = getattr(e, "status", None) or getattr(e, "code", None)
                        if status == 429 or "429" in str(e) or "rate" in str(e).lower():
                            retry_count += 1
                            fallback = base_delay * (2 ** (retry_count - 1))
                            wait_time = parse_retry_after(e, fallback=fallback)

                            LOGGER.warning(
                                f"Twitch rate limit (429). "
                                f"retry_after={wait_time:.0f}s, "
                                f"waiting {format_duration(wait_time)}, "
                                f"attempt={retry_count}/{max_retries}"
                            )
                            LOGGER.debug(f"429 response detail: {str(e)[:500]}")
                            await asyncio.sleep(wait_time)
                        else:
                            raise
                else:
                    LOGGER.error(
                        f"Max retries reached ({max_retries}). Bot cannot connect to Twitch."
                    )
        finally:
            await health_server.stop()
            await db_manager.disconnect()

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        LOGGER.warning("Shutting down due to KeyboardInterrupt...")
    except Exception as e:
        LOGGER.critical(f"Fatal error: {type(e).__name__}: {e}")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
