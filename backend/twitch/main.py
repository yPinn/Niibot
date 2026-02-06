import asyncio
import logging
import sys
from pathlib import Path

import asyncpg
import twitchio
from dotenv import load_dotenv
from twitchio import eventsub
from twitchio.ext import commands

# Ensure shared module is importable (backend/ directory)
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from core import (  # noqa: E402
    COMPONENTS_DIR,
    HealthCheckServer,
    get_channel_subscriptions,
    load_env_config,
    setup_logging,
    validate_env_vars,
)
from shared.database import DatabaseManager, PoolConfig  # noqa: E402
from shared.repositories.analytics import AnalyticsRepository  # noqa: E402
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


class Bot(commands.AutoBot):
    def __init__(
        self, *, token_database: asyncpg.Pool, subs: list[eventsub.SubscriptionPayload]
    ) -> None:
        self.token_database = token_database
        self._subscribed_channels: set[str] = set()
        self._subscription_ids: dict[str, list[str]] = {}

        self.channels = ChannelRepository(token_database)
        self.analytics = AnalyticsRepository(token_database)
        self._active_sessions: dict[str, int] = {}

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
        # 1. 自動載入 components 資料夾下的所有模組
        if COMPONENTS_DIR.exists():
            for file in COMPONENTS_DIR.glob("*.py"):
                if file.stem == "__init__":
                    continue

                # 組合成 components.ai 這種格式
                module_name = f"components.{file.stem}"
                try:
                    await self.load_module(module_name)
                    # print(f"Successfully loaded component: {module_name}")
                except Exception as e:
                    print(f"Failed to load component {module_name}: {e}")

        # 2. 啟動背景任務 (使用 PostgreSQL NOTIFY 即時偵測)
        asyncio.create_task(self._subscribe_initial_channels())
        asyncio.create_task(self.listen_new_token_notifications())
        asyncio.create_task(self.listen_channel_toggle_notifications())

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
                LOGGER.info(f"Owner channel authorized and added: {user.name} (ID: {user.id})")
            else:
                LOGGER.info(f"Channel authorized and added: {user.name} (ID: {user.id})")

        if payload.user_id not in self._subscribed_channels:
            await self.subscribe_channel_events(payload.user_id)
        else:
            LOGGER.debug(f"Channel {payload.user_id} already subscribed, skipping")

    async def event_message(self, payload: twitchio.ChatMessage) -> None:
        if payload.broadcaster:
            LOGGER.debug(f"[{payload.chatter.name}#{payload.broadcaster.name}]: {payload.text}")

            # If channel is not subscribed, ignore the message
            # (This handles race conditions during unsubscribe)
            if payload.broadcaster.id not in self._subscribed_channels:
                LOGGER.debug(
                    f"[BLOCK] Ignoring message from unsubscribed channel: {payload.broadcaster.name}"
                )
                return
        else:
            LOGGER.debug(f"[{payload.chatter.name}]: {payload.text}")

        await super().event_message(payload)

    async def add_token(
        self, token: str, refresh: str
    ) -> twitchio.authentication.ValidateTokenPayload:
        resp: twitchio.authentication.ValidateTokenPayload = await super().add_token(token, refresh)

        if resp.user_id:
            await self.channels.upsert_token_only(resp.user_id, token, refresh)

        login = resp.login or "unknown"
        LOGGER.info(f"Added token to database: {login} ({resp.user_id})")
        return resp

    async def load_tokens(self, path: str | None = None) -> None:
        tokens = await self.channels.list_tokens()

        for tok in tokens:
            try:
                user_info = await self.add_token(tok.token, tok.refresh)
            except twitchio.exceptions.InvalidTokenException as e:
                LOGGER.warning(
                    f"Invalid token for user_id {tok.user_id}, skipping. "
                    f"User needs to re-authenticate: {e}"
                )
                continue

            try:
                await self.add_channel_to_db(tok.user_id, user_info.login or "unknown")
            except Exception as e:
                LOGGER.error(f"Failed to add channel for user_id {tok.user_id}: {e}")

    async def listen_channel_toggle_notifications(self) -> None:
        LOGGER.info("Starting PostgreSQL LISTEN for channel toggle notifications...")

        while True:
            connection = None
            try:
                connection = await self.token_database.acquire()
                await connection.add_listener("channel_toggle", self._handle_channel_toggle)
                LOGGER.info("PostgreSQL LISTEN active on 'channel_toggle' channel")

                try:
                    while True:
                        await asyncio.sleep(60)
                        await connection.execute("SELECT 1")
                except asyncio.CancelledError:
                    LOGGER.info("PostgreSQL LISTEN shutting down...")
                    raise
                finally:
                    try:
                        await connection.remove_listener(
                            "channel_toggle", self._handle_channel_toggle
                        )
                    except Exception:
                        pass
                    await self.token_database.release(connection)
                    connection = None

            except asyncio.CancelledError:
                break
            except Exception as e:
                LOGGER.exception(f"Error in listen_channel_toggle_notifications: {e}")
                LOGGER.warning("Reconnecting to PostgreSQL LISTEN in 10 seconds...")
                if connection is not None:
                    try:
                        await connection.remove_listener(
                            "channel_toggle", self._handle_channel_toggle
                        )
                    except Exception:
                        pass
                    try:
                        await self.token_database.release(connection)
                    except Exception:
                        pass
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    break

    async def _handle_channel_toggle(self, connection, pid, channel, payload) -> None:
        import json

        try:
            LOGGER.info(f"[NOTIFY] Received raw notification on channel '{channel}': {payload}")

            data = json.loads(payload)
            channel_id = data["channel_id"]
            enabled = data["enabled"]

            if channel_id == BOT_ID:
                LOGGER.debug(f"[NOTIFY] Ignoring toggle for bot's own channel: {channel_id}")
                return

            LOGGER.info(
                f"[NOTIFY] Processing channel toggle: {channel_id} -> {'ENABLE' if enabled else 'DISABLE'}"
            )

            if enabled:
                if channel_id not in self._subscribed_channels:
                    await self.subscribe_channel_events(channel_id)
                    LOGGER.info(f"[NOTIFY] ✓ Instantly subscribed to channel: {channel_id}")
                else:
                    LOGGER.info(f"[NOTIFY] Channel {channel_id} already subscribed, skipping")
            else:
                if channel_id in self._subscribed_channels:
                    await self.unsubscribe_channel_events(channel_id)
                    LOGGER.info(f"[NOTIFY] ✓ Instantly unsubscribed from channel: {channel_id}")
                else:
                    LOGGER.info(f"[NOTIFY] Channel {channel_id} not subscribed, skipping")

        except Exception as e:
            LOGGER.exception(f"[NOTIFY] Error handling channel toggle notification: {e}")

    async def _subscribe_initial_channels(self) -> None:
        """Subscribe to EventSub for all enabled channels on startup."""
        try:
            # Small delay to ensure bot is fully initialized
            await asyncio.sleep(2)

            enabled_channels = await self.channels.list_enabled_channels()
            LOGGER.info(f"Subscribing to {len(enabled_channels)} enabled channels...")

            for ch in enabled_channels:
                if ch.channel_id == BOT_ID:
                    continue
                await self.subscribe_channel_events(ch.channel_id)

            LOGGER.info("Initial channel subscription complete")
        except Exception as e:
            LOGGER.exception(f"Error subscribing to initial channels: {e}")

    async def listen_new_token_notifications(self) -> None:
        """Listen for PostgreSQL NOTIFY when new tokens are inserted."""
        LOGGER.info("Starting PostgreSQL LISTEN for new token notifications...")

        while True:
            connection = None
            try:
                connection = await self.token_database.acquire()
                await connection.add_listener("new_token", self._handle_new_token)
                LOGGER.info("PostgreSQL LISTEN active on 'new_token' channel")

                try:
                    while True:
                        await asyncio.sleep(60)
                        await connection.execute("SELECT 1")
                except asyncio.CancelledError:
                    LOGGER.info("New token LISTEN shutting down...")
                    raise
                finally:
                    try:
                        await connection.remove_listener("new_token", self._handle_new_token)
                    except Exception:
                        pass
                    await self.token_database.release(connection)
                    connection = None

            except asyncio.CancelledError:
                break
            except Exception as e:
                LOGGER.exception(f"Error in listen_new_token_notifications: {e}")
                LOGGER.warning("Reconnecting to PostgreSQL LISTEN (new_token) in 10 seconds...")
                if connection is not None:
                    try:
                        await connection.remove_listener("new_token", self._handle_new_token)
                    except Exception:
                        pass
                    try:
                        await self.token_database.release(connection)
                    except Exception:
                        pass
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    break

    async def _handle_new_token(self, connection, pid, channel, payload) -> None:
        """Handle new token notification - load token and subscribe to EventSub."""
        import json

        try:
            LOGGER.info(f"[NOTIFY] Received new token notification: {payload}")

            data = json.loads(payload)
            user_id = data["user_id"]

            if user_id == BOT_ID:
                LOGGER.debug(f"[NOTIFY] Ignoring new token for bot's own account: {user_id}")
                return

            # Fetch the token from database
            token_obj = await self.channels.get_token(user_id)
            if not token_obj:
                LOGGER.warning(f"[NOTIFY] Token not found for user_id: {user_id}")
                return

            # Load token into TwitchIO
            try:
                user_info = await self.add_token(token_obj.token, token_obj.refresh)
                LOGGER.info(f"[NOTIFY] Loaded token for new user: {user_info.login} ({user_id})")

                # Ensure channel exists in database
                await self.add_channel_to_db(user_id, user_info.login or "unknown")

                # Subscribe to EventSub for the new channel
                if user_id not in self._subscribed_channels:
                    await self.subscribe_channel_events(user_id)
                    LOGGER.info(f"[NOTIFY] ✓ Instantly subscribed to new channel: {user_id}")

            except twitchio.exceptions.InvalidTokenException as e:
                LOGGER.warning(f"[NOTIFY] Invalid token for new user {user_id}: {e}")

        except Exception as e:
            LOGGER.exception(f"[NOTIFY] Error handling new token notification: {e}")

    async def setup_database(self) -> None:
        pass

    async def load_channels(self) -> list[str]:
        enabled = await self.channels.list_enabled_channels()
        names = [ch.channel_name for ch in enabled]
        LOGGER.info(f"Loaded {len(names)} channels from database")
        return names

    async def subscribe_channel_events(self, broadcaster_user_id: str) -> None:
        if broadcaster_user_id in self._subscribed_channels:
            LOGGER.debug(f"Already subscribed: {broadcaster_user_id}")
            return

        try:
            subs = get_channel_subscriptions(broadcaster_user_id, BOT_ID)
            resp = await self.multi_subscribe(subs)
            if resp.errors:
                non_conflict = [
                    e for e in resp.errors if "409" not in str(e) and "already exists" not in str(e)
                ]
                if non_conflict:
                    LOGGER.warning(f"Subscription errors: {non_conflict}")

            subscription_ids: list[str] = []
            for success_item in resp.success:
                sub_id = success_item.response.get("id")
                if sub_id and isinstance(sub_id, str):
                    subscription_ids.append(sub_id)

            if subscription_ids:
                self._subscription_ids[broadcaster_user_id] = subscription_ids

            self._subscribed_channels.add(broadcaster_user_id)
            LOGGER.info(f"Subscribed to events for channel: {broadcaster_user_id}")

        except Exception as e:
            LOGGER.exception(f"Failed to subscribe channel {broadcaster_user_id}: {e}")

    async def unsubscribe_channel_events(self, broadcaster_user_id: str) -> None:
        if broadcaster_user_id not in self._subscribed_channels:
            LOGGER.debug(f"Not subscribed to channel: {broadcaster_user_id}")
            return

        try:
            subscription_ids = self._subscription_ids.get(broadcaster_user_id, [])

            if subscription_ids:
                for sub_id in subscription_ids:
                    try:
                        await self.delete_eventsub_subscription(sub_id)
                        LOGGER.debug(
                            f"Deleted subscription {sub_id} for channel {broadcaster_user_id}"
                        )
                    except Exception as e:
                        LOGGER.warning(f"Failed to delete subscription {sub_id}: {e}")

                del self._subscription_ids[broadcaster_user_id]
            else:
                LOGGER.warning(f"No subscription IDs found for channel {broadcaster_user_id}")

            self._subscribed_channels.discard(broadcaster_user_id)
            LOGGER.info(f"Unsubscribed from events for channel: {broadcaster_user_id}")

        except Exception as e:
            LOGGER.exception(f"Failed to unsubscribe channel {broadcaster_user_id}: {e}")

    async def add_channel_to_db(self, channel_id: str, channel_name: str) -> None:
        if channel_id == BOT_ID:
            LOGGER.debug(f"Skipping bot's own channel: {channel_name}")
            return

        await self.channels.upsert_channel(channel_id, channel_name.lower(), enabled=True)
        LOGGER.info(f"Added channel {channel_name} (ID: {channel_id}) to database")

    async def remove_channel_from_db(self, channel_name: str) -> None:
        await self.channels.disable_channel_by_name(channel_name.lower())
        LOGGER.info(f"Disabled channel {channel_name} in database")

    async def event_ready(self) -> None:
        LOGGER.info("Successfully logged in as: %s", self.bot_id)

    async def event_eventsub_notification(
        self,
        payload,
    ) -> None:
        LOGGER.debug(f"EventSub notification received: {type(payload).__name__}")

    async def event_eventsub_ready(self) -> None:
        LOGGER.info("EventSub is ready to receive notifications")

    async def event_eventsub_error(self, error: Exception) -> None:
        LOGGER.error(f"EventSub error: {error}")


def main() -> None:
    setup_logging()

    async def runner() -> None:
        # 1. 啟動 health server（Render 需要儘快偵測到 port）
        health_server = HealthCheckServer()
        await health_server.start()

        # 2. 建立資料庫連線池（使用 shared.database 統一邏輯）
        db_manager = DatabaseManager(
            DATABASE_URL,
            PoolConfig(
                min_size=2,
                max_size=8,
                timeout=60.0,  # Increased for Render ↔ Supabase cross-region
                command_timeout=60.0,
                max_retries=5,
            ),
        )
        await db_manager.connect()
        pool = db_manager.pool

        try:
            subs: list[eventsub.SubscriptionPayload] = []
            channel_repo = ChannelRepository(pool)

            # 3. 重試 DB 連線（Render ↔ Supabase 跨區可能逾時）
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

            # 4. 啟動 Bot，並將 bot 參考設定到 health server（具備自動重試與速率限制保護）
            retry_count = 0
            max_retries = 5
            base_delay = 60  # 起始等待 60 秒

            async with Bot(token_database=pool, subs=subs) as bot:
                if health_server:
                    health_server.bot = bot
                await bot.setup_database()

                while retry_count < max_retries:
                    try:
                        await bot.start()
                        break  # 成功連線則跳出重試迴圈
                    except Exception as e:
                        status = getattr(e, "status", None) or getattr(e, "code", None)
                        if status == 429 or "429" in str(e) or "rate" in str(e).lower():
                            retry_count += 1
                            wait_time = base_delay * (2 ** (retry_count - 1))
                            LOGGER.warning(
                                f"偵測到 Twitch 速率限制 (429)。嘗試第 {retry_count}/{max_retries} 次重試，等待 {wait_time} 秒..."
                            )
                            await asyncio.sleep(wait_time)
                        else:
                            raise
                else:
                    LOGGER.error(
                        f"已達最大重試次數 ({max_retries})，Bot 無法連線至 Twitch。請稍後再試。"
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
