import asyncio
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

import asyncpg
import twitchio
from dotenv import load_dotenv
from twitchio import eventsub
from twitchio.ext import commands

try:
    from rich.console import Console  # noqa: F401
    from rich.logging import RichHandler  # noqa: F401

    RICH_AVAILABLE: bool = True
except ImportError:
    RICH_AVAILABLE = False


if TYPE_CHECKING:
    import asyncpg


LOGGER: logging.Logger = logging.getLogger("Bot")

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)


def validate_env_vars() -> None:
    required_vars = {
        "CLIENT_ID": "Twitch Client ID",
        "CLIENT_SECRET": "Twitch Client Secret",
        "BOT_ID": "Bot User ID",
        "OWNER_ID": "Owner User ID",
        "DATABASE_URL": "Database connection URL",
    }

    missing_vars = []
    for var, description in required_vars.items():
        value = os.getenv(var, "")
        if not value or value.strip() == "":
            missing_vars.append(f"{var} ({description})")

    if missing_vars:
        error_msg = "Missing or empty required environment variables:\n" + "\n".join(
            f"  - {var}" for var in missing_vars
        )
        LOGGER.error(error_msg)
        raise ValueError(error_msg)

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url.startswith("postgresql://"):
        error_msg = "DATABASE_URL must start with 'postgresql://'"
        LOGGER.error(error_msg)
        raise ValueError(error_msg)

    LOGGER.info("All required environment variables validated successfully")


validate_env_vars()

CLIENT_ID: str = os.getenv("CLIENT_ID", "")
CLIENT_SECRET: str = os.getenv("CLIENT_SECRET", "")
BOT_ID: str = os.getenv("BOT_ID", "")
OWNER_ID: str = os.getenv("OWNER_ID", "")
DATABASE_URL: str = os.getenv("DATABASE_URL", "")
CONDUIT_ID: str | None = os.getenv("CONDUIT_ID") or None


class Bot(commands.AutoBot):
    def __init__(
        self, *, token_database: asyncpg.Pool, subs: list[eventsub.SubscriptionPayload]
    ) -> None:
        self.token_database = token_database
        self._subscribed_channels: set[str] = set()
        self._subscription_ids: dict[str, list[str]] = {}
        self.channel_states: dict[str, bool] = {}
        self._channel_states_lock = asyncio.Lock()

        if CONDUIT_ID:
            super().__init__(
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET,
                bot_id=BOT_ID,
                owner_id=OWNER_ID,
                prefix="!",
                subscriptions=subs,
                force_subscribe=True,
                conduit_id=CONDUIT_ID,
            )
        else:
            super().__init__(
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET,
                bot_id=BOT_ID,
                owner_id=OWNER_ID,
                prefix="!",
                subscriptions=subs,
                force_subscribe=True,
            )

    async def setup_hook(self) -> None:
        await self.load_module("components.owner_cmds")
        await self.load_module("components.cmds")
        await self.load_module("components.chat_gpt")
        await self.load_module("components.channel_points")
        await self.load_module("components.event")
        await self.load_module("components.tft")
        await self.load_module("components.sukaoMao")

        asyncio.create_task(self.check_new_tokens_and_channels_task())

    async def event_oauth_authorized(
        self, payload: twitchio.authentication.UserTokenPayload
    ) -> None:
        await self.add_token(payload.access_token, payload.refresh_token)

        if not payload.user_id:
            return

        if payload.user_id == self.bot_id:
            LOGGER.info("Bot account authorized")
            return

        users = await self.fetch_users(ids=[payload.user_id])
        if users:
            user = users[0]
            if user.name:
                await self.add_channel_to_db(user.id, user.name)

            if payload.user_id == self.owner_id:
                LOGGER.info(
                    f"Owner channel authorized and added: {user.name} (ID: {user.id})"
                )
            else:
                LOGGER.info(
                    f"Channel authorized and added: {user.name} (ID: {user.id})"
                )

        if payload.user_id not in self._subscribed_channels:
            await self.subscribe_channel_events(payload.user_id)
        else:
            LOGGER.debug(
                f"Channel {payload.user_id} already subscribed, skipping")

    async def event_message(self, payload: twitchio.ChatMessage) -> None:
        if payload.broadcaster:
            LOGGER.debug(
                f"[{payload.chatter.name}#{payload.broadcaster.name}]: {payload.text}"
            )

            broadcaster_id = payload.broadcaster.id
            async with self._channel_states_lock:
                if broadcaster_id in self.channel_states:
                    is_enabled = self.channel_states[broadcaster_id]
                    if not is_enabled:
                        LOGGER.debug(
                            f"[BLOCK] Ignoring message from disabled channel: {payload.broadcaster.name} ({broadcaster_id})"
                        )
                        return
        else:
            LOGGER.debug(f"[{payload.chatter.name}]: {payload.text}")

        await super().event_message(payload)

    async def add_token(
        self, token: str, refresh: str
    ) -> twitchio.authentication.ValidateTokenPayload:
        resp: twitchio.authentication.ValidateTokenPayload = await super().add_token(
            token, refresh
        )

        query = """
        INSERT INTO tokens (user_id, token, refresh)
        VALUES ($1, $2, $3)
        ON CONFLICT(user_id)
        DO UPDATE SET
            token = excluded.token,
            refresh = excluded.refresh;
        """

        async with self.token_database.acquire() as connection:
            await connection.execute(query, resp.user_id, token, refresh)

        login = resp.login or "unknown"
        LOGGER.info(f"Added token to database: {login} ({resp.user_id})")
        return resp

    async def load_tokens(self, path: str | None = None) -> None:
        async with self.token_database.acquire() as connection:
            rows: list[asyncpg.Record] = await connection.fetch(
                """SELECT * from tokens"""
            )

        for row in rows:
            user_info = await self.add_token(row["token"], row["refresh"])

            try:
                await self.add_channel_to_db(row["user_id"], user_info.login or "unknown")
            except Exception as e:
                LOGGER.error(
                    f"Failed to add channel for user_id {row['user_id']}: {e}")

    async def listen_channel_toggle_notifications(self) -> None:
        LOGGER.info(
            "Starting PostgreSQL LISTEN for channel toggle notifications...")

        while True:
            connection = None
            try:
                connection = await self.token_database.acquire()
                try:
                    await connection.add_listener('channel_toggle', self._handle_channel_toggle)
                    LOGGER.info(
                        "PostgreSQL LISTEN active on 'channel_toggle' channel")

                    while True:
                        await asyncio.sleep(60)
                        await connection.execute("SELECT 1")

                except asyncio.CancelledError:
                    LOGGER.info("PostgreSQL LISTEN shutting down...")
                    try:
                        await connection.remove_listener('channel_toggle', self._handle_channel_toggle)
                    except Exception:
                        pass
                    raise
                finally:
                    await self.token_database.release(connection)

            except asyncio.CancelledError:
                break
            except Exception as e:
                LOGGER.error(
                    f"Error in listen_channel_toggle_notifications: {e}")
                LOGGER.warning(
                    "Reconnecting to PostgreSQL LISTEN in 10 seconds...")
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    break

    async def _handle_channel_toggle(self, connection, pid, channel, payload) -> None:
        import json

        try:
            LOGGER.info(
                f"[NOTIFY] Received raw notification on channel '{channel}': {payload}")

            data = json.loads(payload)
            channel_id = data['channel_id']
            enabled = data['enabled']

            if channel_id == BOT_ID:
                LOGGER.debug(
                    f"[NOTIFY] Ignoring toggle for bot's own channel: {channel_id}")
                return

            LOGGER.info(
                f"[NOTIFY] Processing channel toggle: {channel_id} -> {'ENABLE' if enabled else 'DISABLE'}")

            if enabled:
                if channel_id not in self._subscribed_channels:
                    await self.subscribe_channel_events(channel_id)
                    LOGGER.info(
                        f"[NOTIFY] ✓ Instantly subscribed to channel: {channel_id}")
                else:
                    LOGGER.info(
                        f"[NOTIFY] Channel {channel_id} already subscribed, skipping")
            else:
                if channel_id in self._subscribed_channels:
                    await self.unsubscribe_channel_events(channel_id)
                    LOGGER.info(
                        f"[NOTIFY] ✓ Instantly unsubscribed from channel: {channel_id}")
                else:
                    LOGGER.info(
                        f"[NOTIFY] Channel {channel_id} not subscribed, skipping")

        except Exception as e:
            LOGGER.exception(
                f"[NOTIFY] Error handling channel toggle notification: {e}")

    async def check_new_tokens_and_channels_task(self) -> None:
        loaded_user_ids: set[str] = set()

        try:
            async with self.token_database.acquire() as connection:
                rows = await connection.fetch("SELECT user_id FROM tokens")
                loaded_user_ids = {row["user_id"] for row in rows}

            LOGGER.info(
                f"Token watcher started, tracking {len(loaded_user_ids)} existing users")
        except Exception as e:
            LOGGER.error(f"Failed to initialize token watcher: {e}")
            return

        await asyncio.sleep(5)
        try:
            async with self.token_database.acquire() as connection:
                channel_rows = await connection.fetch(
                    "SELECT channel_id FROM channels WHERE enabled = true"
                )

            for row in channel_rows:
                channel_id = row["channel_id"]
                await self.subscribe_channel_events(channel_id)
                async with self._channel_states_lock:
                    self.channel_states[channel_id] = True
        except Exception as e:
            LOGGER.exception(f"Error subscribing to existing channels: {e}")

        while True:
            try:
                await asyncio.sleep(10)

                async with self.token_database.acquire() as connection:
                    rows = await connection.fetch("SELECT user_id, token, refresh FROM tokens")
                    channel_rows = await connection.fetch(
                        "SELECT channel_id, enabled FROM channels"
                    )

                current_user_ids = {row["user_id"] for row in rows}
                new_user_ids = current_user_ids - loaded_user_ids

                if new_user_ids:
                    LOGGER.info(
                        f"Found {len(new_user_ids)} new users, loading tokens...")

                    for row in rows:
                        if row["user_id"] in new_user_ids:
                            try:
                                user_info = await self.add_token(row["token"], row["refresh"])
                                loaded_user_ids.add(row["user_id"])
                                LOGGER.info(
                                    f"Loaded new token for user_id: {row['user_id']}")

                                await self.add_channel_to_db(
                                    row["user_id"],
                                    user_info.login or "unknown"
                                )

                                await self.subscribe_channel_events(row["user_id"])

                            except Exception as e:
                                LOGGER.error(
                                    f"Failed to load token for user_id {row['user_id']}: {e}")

                for row in channel_rows:
                    channel_id = row["channel_id"]
                    enabled = row["enabled"]

                    if channel_id == BOT_ID:
                        continue

                    async with self._channel_states_lock:
                        previous_state = self.channel_states.get(channel_id)
                        state_changed = previous_state is not None and previous_state != enabled

                        if previous_state is None:
                            self.channel_states[channel_id] = enabled
                        elif state_changed:
                            self.channel_states[channel_id] = enabled

                    if state_changed:
                        LOGGER.info(
                            f"[POLL] Channel {channel_id} state changed: {previous_state} -> {enabled}")

                        if enabled:
                            if channel_id not in self._subscribed_channels:
                                await self.subscribe_channel_events(channel_id)
                                LOGGER.info(
                                    f"[POLL] ✓ Subscribed to channel: {channel_id}")
                        else:
                            if channel_id in self._subscribed_channels:
                                await self.unsubscribe_channel_events(channel_id)
                                LOGGER.info(
                                    f"[POLL] ✓ Unsubscribed from channel: {channel_id}")

            except (asyncio.CancelledError, KeyboardInterrupt):
                LOGGER.info("Token watcher shutting down...")
                break
            except Exception as e:
                LOGGER.error(f"Error in check_new_tokens_task: {e}")
                try:
                    await asyncio.sleep(60)
                except (asyncio.CancelledError, KeyboardInterrupt):
                    LOGGER.info("Token watcher shutting down...")
                    break

    async def setup_database(self) -> None:
        pass

    async def load_channels(self) -> list[str]:
        async with self.token_database.acquire() as connection:
            rows: list[asyncpg.Record] = await connection.fetch(
                """SELECT channel_name FROM channels WHERE enabled = true"""
            )

        channels = [row["channel_name"] for row in rows]
        LOGGER.info(f"Loaded {len(channels)} channels from database")
        return channels

    async def subscribe_channel_events(self, broadcaster_user_id: str) -> None:
        if broadcaster_user_id in self._subscribed_channels:
            LOGGER.debug(f"Already subscribed: {broadcaster_user_id}")
            return

        try:
            subs = [
                eventsub.ChatMessageSubscription(
                    broadcaster_user_id=broadcaster_user_id, user_id=BOT_ID
                ),
                eventsub.StreamOnlineSubscription(
                    broadcaster_user_id=broadcaster_user_id
                ),
                eventsub.ChannelPointsRedeemAddSubscription(
                    broadcaster_user_id=broadcaster_user_id
                ),
                eventsub.ChannelFollowSubscription(
                    broadcaster_user_id=broadcaster_user_id,
                    moderator_user_id=BOT_ID
                ),
                eventsub.ChannelSubscribeSubscription(
                    broadcaster_user_id=broadcaster_user_id
                ),
            ]

            resp = await self.multi_subscribe(subs)
            if resp.errors:
                non_conflict = [e for e in resp.errors if "409" not in str(
                    e) and "already exists" not in str(e)]
                if non_conflict:
                    LOGGER.warning(f"Subscription errors: {non_conflict}")

            subscription_ids: list[str] = []
            for success_item in resp.success:
                sub_id = success_item.response.get('id')
                if sub_id and isinstance(sub_id, str):
                    subscription_ids.append(sub_id)

            if subscription_ids:
                self._subscription_ids[broadcaster_user_id] = subscription_ids

            self._subscribed_channels.add(broadcaster_user_id)
            LOGGER.info(
                f"Subscribed to events for channel: {broadcaster_user_id}")

        except Exception as e:
            LOGGER.exception(
                f"Failed to subscribe channel {broadcaster_user_id}: {e}")

    async def unsubscribe_channel_events(self, broadcaster_user_id: str) -> None:
        if broadcaster_user_id not in self._subscribed_channels:
            LOGGER.debug(f"Not subscribed to channel: {broadcaster_user_id}")
            return

        try:
            subscription_ids = self._subscription_ids.get(
                broadcaster_user_id, [])

            if subscription_ids:
                for sub_id in subscription_ids:
                    try:
                        await self.delete_eventsub_subscription(sub_id)
                        LOGGER.debug(
                            f"Deleted subscription {sub_id} for channel {broadcaster_user_id}")
                    except Exception as e:
                        LOGGER.warning(
                            f"Failed to delete subscription {sub_id}: {e}")

                del self._subscription_ids[broadcaster_user_id]
            else:
                LOGGER.warning(
                    f"No subscription IDs found for channel {broadcaster_user_id}")

            self._subscribed_channels.discard(broadcaster_user_id)
            LOGGER.info(
                f"Unsubscribed from events for channel: {broadcaster_user_id}")

        except Exception as e:
            LOGGER.exception(
                f"Failed to unsubscribe channel {broadcaster_user_id}: {e}")

    async def add_channel_to_db(self, channel_id: str, channel_name: str) -> None:
        if channel_id == BOT_ID:
            LOGGER.debug(f"Skipping bot's own channel: {channel_name}")
            return

        query = """
        INSERT INTO channels (channel_id, channel_name, enabled)
        VALUES ($1, $2, true)
        ON CONFLICT(channel_id)
        DO UPDATE SET
            channel_name = excluded.channel_name,
            enabled = true;
        """

        async with self.token_database.acquire() as connection:
            await connection.execute(query, channel_id, channel_name.lower())

        LOGGER.info(
            f"Added channel {channel_name} (ID: {channel_id}) to database")

    async def remove_channel_from_db(self, channel_name: str) -> None:
        query = """UPDATE channels SET enabled = false WHERE channel_name = $1"""

        async with self.token_database.acquire() as connection:
            await connection.execute(query, channel_name.lower())

        LOGGER.info(f"Disabled channel {channel_name} in database")

    async def event_ready(self) -> None:
        LOGGER.info("Successfully logged in as: %s", self.bot_id)

    async def event_eventsub_notification(
        self,
        payload,
    ) -> None:
        LOGGER.debug(
            f"EventSub notification received: {type(payload).__name__}")

    async def event_eventsub_ready(self) -> None:
        LOGGER.info("EventSub is ready to receive notifications")

    async def event_eventsub_error(self, error: Exception) -> None:
        LOGGER.error(f"EventSub error: {error}")


def setup_logging() -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level, logging.INFO)

    if RICH_AVAILABLE:
        try:
            from rich.console import Console
            from rich.logging import RichHandler

            console = Console(
                force_terminal=True,
                color_system="auto",
                width=120,
            )

            rich_handler = RichHandler(
                console=console,
                show_time=True,
                show_level=True,
                show_path=True,
                markup=True,
                rich_tracebacks=True,
                tracebacks_show_locals=False,
                tracebacks_width=120,
            )

            rich_handler.setFormatter(
                logging.Formatter(fmt="%(message)s",
                                  datefmt="[%Y-%m-%d %H:%M:%S]")
            )

            logging.basicConfig(
                level=level,
                format="%(message)s",
                datefmt="[%Y-%m-%d %H:%M:%S]",
                handlers=[rich_handler],
            )
            LOGGER.info(
                "[bold green]✓[/bold green] Rich logging enabled",
                extra={"markup": True},
            )
        except Exception as e:
            logging.basicConfig(
                level=level,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            LOGGER.warning(
                f"Failed to setup Rich logging: {e}, using standard logging")
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        LOGGER.info(
            "Standard logging enabled (install 'rich' for better output)")

    if level == logging.DEBUG:
        logging.getLogger("twitchio").setLevel(logging.DEBUG)
        logging.getLogger("twitchio.eventsub").setLevel(logging.DEBUG)
        logging.getLogger("twitchio.http").setLevel(logging.DEBUG)
        logging.getLogger("twitchio.websockets").setLevel(logging.DEBUG)
        logging.getLogger("httpx").setLevel(logging.INFO)
    else:
        logging.getLogger("twitchio").setLevel(logging.INFO)
        logging.getLogger("twitchio.eventsub").setLevel(logging.INFO)
        logging.getLogger("twitchio.http").setLevel(logging.WARNING)
        logging.getLogger("twitchio.websockets").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)

    logging.getLogger("asyncio").setLevel(logging.ERROR)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


def main() -> None:
    setup_logging()

    async def runner() -> None:
        pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=1, max_size=10, statement_cache_size=0
        )
        if pool is None:
            LOGGER.error("Failed to create database connection pool")
            return

        try:
            subs: list[eventsub.SubscriptionPayload] = []

            async with pool.acquire() as connection:
                await connection.execute(
                    """CREATE TABLE IF NOT EXISTS tokens(
                        user_id TEXT PRIMARY KEY,
                        token TEXT NOT NULL,
                        refresh TEXT NOT NULL
                    )"""
                )
                await connection.execute(
                    """CREATE TABLE IF NOT EXISTS channels(
                        channel_id TEXT PRIMARY KEY,
                        channel_name TEXT NOT NULL UNIQUE,
                        enabled BOOLEAN DEFAULT true,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )"""
                )

                await connection.execute(
                    """
                    CREATE OR REPLACE FUNCTION notify_channel_toggle()
                    RETURNS TRIGGER AS $$
                    DECLARE
                        payload TEXT;
                    BEGIN
                        IF NEW.enabled IS DISTINCT FROM OLD.enabled THEN
                            payload := json_build_object(
                                'channel_id', NEW.channel_id,
                                'channel_name', NEW.channel_name,
                                'enabled', NEW.enabled
                            )::text;

                            PERFORM pg_notify('channel_toggle', payload);
                        END IF;

                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                    """
                )

                await connection.execute(
                    """
                    DROP TRIGGER IF EXISTS channel_toggle_trigger ON channels;
                    CREATE TRIGGER channel_toggle_trigger
                    AFTER UPDATE ON channels
                    FOR EACH ROW
                    EXECUTE FUNCTION notify_channel_toggle();
                    """
                )

                rows = await connection.fetch(
                    """SELECT channel_id FROM channels WHERE enabled = true"""
                )

                for row in rows:
                    broadcaster_user_id = row["channel_id"]
                    if broadcaster_user_id == BOT_ID:
                        continue

                    subs.extend(
                        [
                            eventsub.ChatMessageSubscription(
                                broadcaster_user_id=broadcaster_user_id, user_id=BOT_ID
                            ),
                            eventsub.StreamOnlineSubscription(
                                broadcaster_user_id=broadcaster_user_id
                            ),
                            eventsub.ChannelPointsRedeemAddSubscription(
                                broadcaster_user_id=broadcaster_user_id
                            ),
                            eventsub.ChannelFollowSubscription(
                                broadcaster_user_id=broadcaster_user_id,
                                moderator_user_id=BOT_ID
                            ),
                            eventsub.ChannelSubscribeSubscription(
                                broadcaster_user_id=broadcaster_user_id
                            ),
                        ]
                    )

            LOGGER.info(f"Starting bot with {len(subs)} initial subscriptions")

            async with Bot(token_database=pool, subs=subs) as bot:
                await bot.setup_database()
                await bot.start()
        finally:
            await pool.close()

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        LOGGER.warning("Shutting down due to KeyboardInterrupt...")


if __name__ == "__main__":
    main()
