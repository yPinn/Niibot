"""Twitch bot launcher — entry point only."""

import asyncio
import logging
import sys
from pathlib import Path

# Ensure shared module is importable (backend/ directory)
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)


def main() -> None:
    # Minimal imports for health server — bind port ASAP for Render
    from core.health_server import HealthCheckServer
    from core.logging import setup_logging

    setup_logging()

    async def runner() -> None:
        # 1. Health server FIRST (Render needs a port quickly)
        health_server = HealthCheckServer()
        await health_server.start()

        # 2. Heavy imports — after port is open
        import logging

        from dotenv import load_dotenv
        from twitchio import eventsub

        from core import get_channel_subscriptions, load_env_config, validate_env_vars
        from core.bot import Bot
        from shared.database import DatabaseManager, PoolConfig
        from shared.repositories.channel import ChannelRepository

        logger = logging.getLogger("Bot")

        env_path = Path(__file__).parent / ".env"
        load_dotenv(dotenv_path=env_path)
        validate_env_vars()
        env_config = load_env_config()

        client_id: str = env_config["CLIENT_ID"]
        client_secret: str = env_config["CLIENT_SECRET"]
        bot_id: str = env_config["BOT_ID"]
        owner_id: str = env_config["OWNER_ID"]
        database_url: str = env_config["DATABASE_URL"]
        conduit_id: str | None = env_config["CONDUIT_ID"] or None

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
                    logger.warning(f"Database connect attempt ({attempt}/5): {type(e).__name__}")
                    if attempt < 5:
                        await asyncio.sleep(5)

            if subs:
                logger.info(f"Starting bot with {len(subs)} initial subscriptions")
            else:
                logger.warning(
                    "Starting bot without initial subscriptions (DB unavailable or empty)"
                )
                logger.warning("Background task will load channels once DB is reachable")

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
                subs=subs,
            ) as bot:
                if health_server:
                    health_server.bot = bot
                await bot.setup_database()

                while retry_count < max_retries:
                    try:
                        await bot.start()
                        break
                    except Exception as e:
                        status = getattr(e, "status", None) or getattr(e, "code", None)
                        if status == 429 or "429" in str(e) or "rate" in str(e).lower():
                            retry_count += 1

                            # Extract retry_after from response if available
                            retry_after = base_delay * (2 ** (retry_count - 1))
                            resp = getattr(e, "response", None)
                            if resp:
                                headers = getattr(resp, "headers", {})
                                for key in ("Retry-After", "retry-after", "retry_after"):
                                    if key in headers:
                                        try:
                                            retry_after = float(headers[key])
                                        except (ValueError, TypeError):
                                            pass
                                        break
                            if hasattr(e, "retry_after"):
                                try:
                                    retry_after = float(e.retry_after)
                                except (ValueError, TypeError):
                                    pass

                            wait_time = max(retry_after, base_delay * (2 ** (retry_count - 1)))

                            # Human-readable duration
                            secs = int(wait_time)
                            if secs >= 3600:
                                readable = f"{secs // 3600}h{(secs % 3600) // 60}m"
                            elif secs >= 60:
                                readable = f"{secs // 60}m{secs % 60}s"
                            else:
                                readable = f"{secs}s"

                            logger.warning(
                                f"Twitch rate limit (429). "
                                f"retry_after={retry_after:.0f}s, "
                                f"waiting {readable}, "
                                f"attempt={retry_count}/{max_retries}"
                            )

                            # Log raw error for debugging
                            err_text = str(e)[:500]
                            if err_text:
                                logger.info(f"[429 Response] {err_text}")

                            await asyncio.sleep(wait_time)
                        else:
                            raise
                else:
                    logger.error(
                        f"Max retries reached ({max_retries}). Bot cannot connect to Twitch."
                    )
        finally:
            if health_server:
                await health_server.stop()
            await db_manager.disconnect()

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        logging.getLogger("Bot").warning("Shutting down due to KeyboardInterrupt...")


if __name__ == "__main__":
    main()
