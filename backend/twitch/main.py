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

# Load environment variables from twitch/.env file
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)


def validate_env_vars() -> None:
    """Validate required environment variables are set and not empty."""
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

    # Validate DATABASE_URL format
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url.startswith("postgresql://"):
        error_msg = "DATABASE_URL must start with 'postgresql://'"
        LOGGER.error(error_msg)
        raise ValueError(error_msg)

    LOGGER.info("All required environment variables validated successfully")


# Validate environment variables before use
validate_env_vars()

CLIENT_ID: str = os.getenv("CLIENT_ID", "")
CLIENT_SECRET: str = os.getenv("CLIENT_SECRET", "")
BOT_ID: str = os.getenv("BOT_ID", "")
OWNER_ID: str = os.getenv("OWNER_ID", "")
DATABASE_URL: str = os.getenv("DATABASE_URL", "")
CONDUIT_ID: str | None = os.getenv("CONDUIT_ID") or None


class Bot(commands.AutoBot):
    # AutoBot automatically creates and connects to a Conduit for EventSub
    # Conduits make it easier to manage subscriptions - they last 72 hours after shutdown

    def __init__(
        self, *, token_database: asyncpg.Pool, subs: list[eventsub.SubscriptionPayload]
    ) -> None:
        self.token_database = token_database

        # Only add conduit_id if it's explicitly set
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
        # Load the module that contains our component, commands, and listeners.
        # Modules can have multiple components.
        await self.load_module("components.owner_cmds")
        await self.load_module("components.cmds")
        await self.load_module("components.chat_gpt")
        await self.load_module("components.channel_points")
        await self.load_module("components.event")
        await self.load_module("components.tft")
        await self.load_module("components.sukaoMao")

        # 啟動定時任務:檢查新 token
        asyncio.create_task(self.check_new_tokens_task())

    async def event_oauth_authorized(
        self, payload: twitchio.authentication.UserTokenPayload
    ) -> None:
        """Handle OAuth authorization for multi-channel support.

        When a user authorizes the bot via OAuth:
        - payload.user_id is the Twitch user_id of the authorizing user
        - In Twitch, user_id == broadcaster_user_id == channel_id (they're the same concept)
        - We store this in the channels table as channel_id
        """
        await self.add_token(payload.access_token, payload.refresh_token)

        if not payload.user_id:
            return

        if payload.user_id == self.bot_id:
            # We usually don't want to subscribe to events on the bot's channel
            LOGGER.info("Bot account authorized")
            return

        # Fetch user details to get the username
        # payload.user_id == user.id (both are the same Twitch user_id)
        users = await self.fetch_users(ids=[payload.user_id])
        if users:
            user = users[0]
            # Store: user.id (user_id) as channel_id, user.name as channel_name
            if user.name:
                await self.add_channel_to_db(user.id, user.name)

            # Log with owner indicator if this is the owner's channel
            if payload.user_id == self.owner_id:
                LOGGER.info(
                    f"Owner channel authorized and added: {user.name} (ID: {user.id})"
                )
            else:
                LOGGER.info(
                    f"Channel authorized and added: {user.name} (ID: {user.id})"
                )

        subs: list[eventsub.SubscriptionPayload] = [
            eventsub.ChatMessageSubscription(
                broadcaster_user_id=payload.user_id, user_id=self.bot_id
            ),
            eventsub.StreamOnlineSubscription(broadcaster_user_id=payload.user_id),
            eventsub.ChannelPointsRedeemAddSubscription(
                broadcaster_user_id=payload.user_id
            ),
            eventsub.ChannelFollowSubscription(
                broadcaster_user_id=payload.user_id,
                moderator_user_id=self.bot_id
            ),
            eventsub.ChannelSubscribeSubscription(
                broadcaster_user_id=payload.user_id
            ),
        ]

        resp: twitchio.MultiSubscribePayload = await self.multi_subscribe(subs)
        if resp.errors:
            non_conflict_errors = [
                err
                for err in resp.errors
                if "409" not in str(err.error)
                and "already exists" not in str(err.error)
            ]

            if non_conflict_errors:
                # 只有非 409 錯誤才記錄為 WARNING
                LOGGER.warning(
                    f"Failed to subscribe to: {non_conflict_errors}, for user: {payload.user_id}"
                )
            else:
                # 所有錯誤都是 409（訂閱已存在），記錄為 DEBUG
                LOGGER.debug(
                    f"EventSub subscriptions already exist for user: {payload.user_id}"
                )

    async def event_message(self, payload: twitchio.ChatMessage) -> None:
        """Handle incoming chat messages."""
        # payload.broadcaster 是 PartialUser，代表接收訊息的頻道
        if payload.broadcaster:
            LOGGER.debug(
                f"[{payload.chatter.name}#{payload.broadcaster.name}]: {payload.text}"
            )
        else:
            LOGGER.debug(f"[{payload.chatter.name}]: {payload.text}")
        await super().event_message(payload)

    async def add_token(
        self, token: str, refresh: str
    ) -> twitchio.authentication.ValidateTokenPayload:
        # Make sure to call super() as it will add the tokens interally and return us some data...
        resp: twitchio.authentication.ValidateTokenPayload = await super().add_token(
            token, refresh
        )

        # Store our tokens in PostgreSQL Database when they are authorized...
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

        # Log with username
        login = resp.login or "unknown"
        LOGGER.info(f"Added token to database: {login} ({resp.user_id})")
        return resp

    async def load_tokens(self, path: str | None = None) -> None:
        # We don't need to call this manually, it is called in .login() from .start() internally...

        async with self.token_database.acquire() as connection:
            rows: list[asyncpg.Record] = await connection.fetch(
                """SELECT * from tokens"""
            )

        for row in rows:
            await self.add_token(row["token"], row["refresh"])

    async def check_new_tokens_task(self) -> None:
        """定時檢查資料庫中的新 token 並載入

        每 30 秒檢查一次資料庫,如果有新的 token 就載入
        """
        # 記錄已載入的 user_ids
        loaded_user_ids: set[str] = set()

        # 初始化:載入當前所有 user_ids
        async with self.token_database.acquire() as connection:
            rows = await connection.fetch("SELECT user_id FROM tokens")
            loaded_user_ids = {row["user_id"] for row in rows}

        LOGGER.info(f"Token watcher started, tracking {len(loaded_user_ids)} existing users")

        while True:
            try:
                await asyncio.sleep(30)  # 每 30 秒檢查一次

                async with self.token_database.acquire() as connection:
                    rows = await connection.fetch("SELECT user_id, token, refresh FROM tokens")

                current_user_ids = {row["user_id"] for row in rows}
                new_user_ids = current_user_ids - loaded_user_ids

                if new_user_ids:
                    LOGGER.info(f"Found {len(new_user_ids)} new users, loading tokens...")

                    for row in rows:
                        if row["user_id"] in new_user_ids:
                            try:
                                await self.add_token(row["token"], row["refresh"])
                                loaded_user_ids.add(row["user_id"])
                                LOGGER.info(f"Loaded new token for user_id: {row['user_id']}")
                            except Exception as e:
                                LOGGER.error(f"Failed to load token for user_id {row['user_id']}: {e}")

            except Exception as e:
                LOGGER.exception(f"Error in check_new_tokens_task: {e}")
                await asyncio.sleep(60)  # 發生錯誤時等待更久

    async def setup_database(self) -> None:
        # Create our token table, if it doesn't exist..
        query_tokens = """CREATE TABLE IF NOT EXISTS tokens(user_id TEXT PRIMARY KEY, token TEXT NOT NULL, refresh TEXT NOT NULL)"""

        # Create channels table for multi-channel support
        query_channels = """
        CREATE TABLE IF NOT EXISTS channels(
            channel_id TEXT PRIMARY KEY,
            channel_name TEXT NOT NULL UNIQUE,
            enabled BOOLEAN DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )"""

        async with self.token_database.acquire() as connection:
            await connection.execute(query_tokens)
            await connection.execute(query_channels)

    async def load_channels(self) -> list[str]:
        """Load enabled channels from database."""
        async with self.token_database.acquire() as connection:
            rows: list[asyncpg.Record] = await connection.fetch(
                """SELECT channel_name FROM channels WHERE enabled = true"""
            )

        channels = [row["channel_name"] for row in rows]
        LOGGER.info(f"Loaded {len(channels)} channels from database")
        return channels

    async def add_channel_to_db(self, channel_id: str, channel_name: str) -> None:
        """Add a channel to the database.

        Args:
            channel_id: Twitch user_id (same as broadcaster_user_id)
            channel_name: Lowercase Twitch username
        """
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

        LOGGER.info(f"Added channel {channel_name} (ID: {channel_id}) to database")

    async def remove_channel_from_db(self, channel_name: str) -> None:
        """Disable a channel in the database."""
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
        """記錄所有 EventSub 通知以進行調試"""
        LOGGER.debug(f"EventSub notification received: {type(payload).__name__}")

    async def event_eventsub_ready(self) -> None:
        """EventSub 已準備好接收通知"""
        LOGGER.info("EventSub is ready to receive notifications")

    async def event_eventsub_error(self, error: Exception) -> None:
        """EventSub 發生錯誤"""
        LOGGER.error(f"EventSub error: {error}")


def setup_logging() -> None:
    """設置日誌系統，優先使用 Rich，否則使用標準日誌。"""
    # 獲取日誌級別（可從環境變數設定，預設 INFO）
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level, logging.INFO)

    if RICH_AVAILABLE:
        try:
            from rich.console import Console
            from rich.logging import RichHandler

            # 使用 Rich 提供更美觀的輸出
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
                tracebacks_show_locals=False,  # 生產環境設為 False
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
            LOGGER.info(
                "[bold green]✓[/bold green] Rich logging enabled",
                extra={"markup": True},
            )
        except Exception as e:
            # Fallback 到標準日誌
            logging.basicConfig(
                level=level,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            LOGGER.warning(f"Failed to setup Rich logging: {e}, using standard logging")
    else:
        # 使用標準日誌格式
        logging.basicConfig(
            level=level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        LOGGER.info("Standard logging enabled (install 'rich' for better output)")

    # 調整第三方庫的日誌級別
    # 開發模式 (LOG_LEVEL=DEBUG) 時啟用詳細日誌
    if level == logging.DEBUG:
        logging.getLogger("twitchio").setLevel(logging.DEBUG)
        logging.getLogger("twitchio.eventsub").setLevel(logging.DEBUG)
        logging.getLogger("twitchio.http").setLevel(logging.DEBUG)
        logging.getLogger("twitchio.websockets").setLevel(logging.DEBUG)
        logging.getLogger("httpx").setLevel(logging.INFO)
    else:
        # 生產模式 (LOG_LEVEL=INFO) 減少噪音
        logging.getLogger("twitchio").setLevel(logging.INFO)
        logging.getLogger("twitchio.eventsub").setLevel(logging.INFO)
        logging.getLogger("twitchio.http").setLevel(logging.WARNING)
        logging.getLogger("twitchio.websockets").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)

    # 這些庫始終保持 WARNING/ERROR
    logging.getLogger("asyncio").setLevel(logging.ERROR)  # 隱藏 Windows socket 警告
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


def main() -> None:
    setup_logging()

    async def runner() -> None:
        # Create PostgreSQL connection pool
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
        if pool is None:
            LOGGER.error("Failed to create database connection pool")
            return

        try:
            # Load existing tokens and generate subscriptions for each authorized user
            subs: list[eventsub.SubscriptionPayload] = []

            async with pool.acquire() as connection:
                # Ensure tables exist
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

                # Get all enabled channels for initial subscriptions
                # Note: channel_id in database == broadcaster_user_id in TwitchIO
                rows = await connection.fetch(
                    """SELECT channel_id FROM channels WHERE enabled = true"""
                )

                for row in rows:
                    # This is the channel owner's user_id
                    broadcaster_user_id = row["channel_id"]
                    if broadcaster_user_id == BOT_ID:
                        continue

                    # Create EventSub subscriptions for each authorized channel
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
