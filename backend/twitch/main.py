"""Twitch bot launcher — entry point only."""

import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from twitchio import eventsub

# Ensure shared module is importable (backend/ directory)
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from core import (  # noqa: E402
    HealthCheckServer,
    get_channel_subscriptions,
    load_env_config,
    setup_logging,
    validate_env_vars,
)
from core.bot import Bot  # noqa: E402
from shared.database import DatabaseManager, PoolConfig  # noqa: E402
from shared.repositories.channel import ChannelRepository  # noqa: E402

LOGGER: logging.Logger = logging.getLogger("Bot")

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

validate_env_vars()
env_config = load_env_config()

CLIENT_ID: str = env_config["CLIENT_ID"]
CLIENT_SECRET: str = env_config["CLIENT_SECRET"]
BOT_ID: str = env_config["BOT_ID"]
OWNER_ID: str = env_config["OWNER_ID"]
DATABASE_URL: str = env_config["DATABASE_URL"]
CONDUIT_ID: str | None = env_config["CONDUIT_ID"] or None


def main() -> None:
    setup_logging()

    async def runner() -> None:
        # 1. Health server (Render needs a port quickly)
        health_server = HealthCheckServer()
        await health_server.start()

        # 2. Database connection pool
        db_manager = DatabaseManager(
            DATABASE_URL,
            PoolConfig(
                min_size=2,
                max_size=8,
                timeout=60.0,
                command_timeout=60.0,
                max_retries=5,
            ),
        )
        await db_manager.connect()
        pool = db_manager.pool

        try:
            subs: list[eventsub.SubscriptionPayload] = []
            channel_repo = ChannelRepository(pool)

            # 3. Retry DB connection (cross-region timeout)
            for attempt in range(1, 6):
                try:
                    enabled_channels = await channel_repo.list_enabled_channels()
                    for ch in enabled_channels:
                        if ch.channel_id == BOT_ID:
                            continue
                        subs.extend(get_channel_subscriptions(ch.channel_id, BOT_ID))
                    break
                except (TimeoutError, OSError) as e:
                    LOGGER.warning(f"Database connect attempt ({attempt}/5): {type(e).__name__}")
                    if attempt < 5:
                        await asyncio.sleep(5)

            if subs:
                LOGGER.info(f"Starting bot with {len(subs)} initial subscriptions")
            else:
                LOGGER.warning(
                    "Starting bot without initial subscriptions (DB unavailable or empty)"
                )
                LOGGER.warning("Background task will load channels once DB is reachable")

            # 4. Start bot with auto-retry on rate limit
            retry_count = 0
            max_retries = 5
            base_delay = 60

            async with Bot(
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET,
                bot_id=BOT_ID,
                owner_id=OWNER_ID,
                conduit_id=CONDUIT_ID,
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
                            wait_time = base_delay * (2 ** (retry_count - 1))
                            LOGGER.warning(
                                f"Twitch rate limit (429). "
                                f"Retry {retry_count}/{max_retries}, waiting {wait_time}s..."
                            )
                            await asyncio.sleep(wait_time)
                        else:
                            raise
                else:
                    LOGGER.error(
                        f"Max retries reached ({max_retries}). Bot cannot connect to Twitch."
                    )
        finally:
            if health_server:
                await health_server.stop()
            await db_manager.disconnect()

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        LOGGER.warning("Shutting down due to KeyboardInterrupt...")


if __name__ == "__main__":
    main()
