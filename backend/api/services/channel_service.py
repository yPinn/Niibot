"""Channel management service"""

import logging

import asyncpg
from backend.api.services.twitch_api import TwitchAPIClient

logger = logging.getLogger(__name__)


class ChannelService:
    """Handle channel-related database operations"""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_channel_status(self, user_id: str) -> dict:
        """Get channel status for a user"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT channel_id, channel_name, enabled
                    FROM channels
                    WHERE channel_id = $1
                    """,
                    user_id,
                )

                if row and row["enabled"]:
                    return {
                        "subscribed": True,
                        "channel_id": row["channel_id"],
                        "channel_name": row["channel_name"],
                    }
                else:
                    return {
                        "subscribed": False,
                        "channel_id": user_id,
                        "channel_name": row["channel_name"] if row else "",
                    }

        except Exception as e:
            logger.exception(f"Error getting channel status for user {user_id}: {e}")
            return {
                "subscribed": False,
                "channel_id": user_id,
                "channel_name": "",
            }

    async def toggle_channel(self, channel_id: str, enabled: bool) -> bool:
        """Enable or disable a channel"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE channels
                    SET enabled = $1, updated_at = CURRENT_TIMESTAMP
                    WHERE channel_id = $2
                    """,
                    enabled,
                    channel_id,
                )

            action = "enabled" if enabled else "disabled"
            logger.debug(f"Channel {channel_id} {action}")
            return True

        except Exception as e:
            logger.exception(f"Error toggling channel {channel_id}: {e}")
            return False

    async def get_enabled_channels(self) -> list[dict]:
        """Get all enabled channels"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT channel_id, channel_name FROM channels WHERE enabled = true"
                )

                return [
                    {"channel_id": row["channel_id"], "channel_name": row["channel_name"]}
                    for row in rows
                ]

        except Exception as e:
            logger.exception(f"Error getting enabled channels: {e}")
            return []

    async def get_user_token(self, user_id: str) -> str | None:
        """Get user's access token from database"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT token FROM tokens WHERE user_id = $1",
                    user_id,
                )

                return row["token"] if row else None

        except Exception as e:
            logger.exception(f"Error getting token for user {user_id}: {e}")
            return None

    async def save_token(
        self, user_id: str, access_token: str, refresh_token: str, username: str = ""
    ) -> bool:
        """Save or update user's OAuth token"""
        try:
            async with self.pool.acquire() as conn:
                # 使用 Transaction 確保兩張表同步更新，若其中一個失敗則全部回滾
                async with conn.transaction():
                    # 1. 更新 tokens 表
                    await conn.execute(
                        """
                        INSERT INTO tokens (user_id, token, refresh)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (user_id)
                        DO UPDATE SET
                            token = EXCLUDED.token,
                            refresh = EXCLUDED.refresh,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        user_id,
                        access_token,
                        refresh_token,
                    )

                    # 2. 更新 channels 表 (確保頻道已註冊並更新名字)
                    await conn.execute(
                        """
                    INSERT INTO channels (channel_id, channel_name, enabled, created_at)
                    VALUES ($1, $2, true, NOW())
                    ON CONFLICT (channel_id)
                    DO UPDATE SET
                        channel_name = EXCLUDED.channel_name,
                        updated_at = CURRENT_TIMESTAMP
                """,
                        user_id,
                        username,
                    )

            logger.info(f"Successfully synced token and channel for: {username} ({user_id})")
            return True

        except Exception as e:
            logger.exception(f"Error in save_token transaction: {e}")
            return False

    async def save_discord_user(
        self,
        user_id: str,
        username: str,
        display_name: str | None = None,
        avatar: str | None = None,
    ) -> bool:
        """Save or update Discord user info"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO discord_users (user_id, username, display_name, avatar)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id)
                    DO UPDATE SET
                        username = EXCLUDED.username,
                        display_name = EXCLUDED.display_name,
                        avatar = EXCLUDED.avatar,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    user_id,
                    username,
                    display_name,
                    avatar,
                )

            logger.debug(f"Discord user saved: {username} ({user_id})")
            return True

        except Exception as e:
            logger.exception(f"Error saving Discord user to database: {e}")
            return False

    async def get_discord_user(self, user_id: str) -> dict[str, str] | None:
        """Get Discord user info from database"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT user_id, username, display_name, avatar
                    FROM discord_users
                    WHERE user_id = $1
                    """,
                    user_id,
                )

                if not row:
                    return None

                # Build avatar URL
                avatar_url = self._get_discord_avatar_url(row["user_id"], row["avatar"])

                return {
                    "id": row["user_id"],
                    "name": row["username"],
                    "display_name": row["display_name"] or row["username"],
                    "avatar": avatar_url,
                }

        except Exception as e:
            logger.exception(f"Error getting Discord user {user_id}: {e}")
            return None

    def _get_discord_avatar_url(self, user_id: str, avatar_hash: str | None) -> str:
        """Generate Discord avatar URL"""
        if avatar_hash:
            ext = "gif" if avatar_hash.startswith("a_") else "png"
            return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}"
        # Default avatar
        default_avatar_index = int(user_id) % 5
        return f"https://cdn.discordapp.com/embed/avatars/{default_avatar_index}.png"

    async def sync_empty_names(self, twitch_api: TwitchAPIClient):
        """找出名字為空的頻道並從 Twitch 更新"""
        try:
            async with self.pool.acquire() as conn:
                # 1. 找出所有名稱為空或 NULL 的 ID
                rows = await conn.fetch(
                    "SELECT channel_id FROM channels WHERE channel_name IS NULL OR channel_name = ''"
                )

                if not rows:
                    logger.debug("No empty channel names to sync.")
                    return

                logger.info(f"Found {len(rows)} channels with empty names. Starting sync...")

                for row in rows:
                    cid = row["channel_id"]
                    try:
                        # 2. 向 Twitch API 查詢資訊
                        user_info = await twitch_api.get_user_info(cid)
                        if user_info:
                            # 優先取顯示名稱，沒有則取登入名稱
                            new_name = (
                                user_info.get("display_name")
                                or user_info.get("login")
                                or user_info.get("name")
                            )

                            if new_name:
                                # 3. 更新回資料庫
                                await conn.execute(
                                    "UPDATE channels SET channel_name = $1, updated_at = NOW() WHERE channel_id = $2",
                                    new_name,
                                    cid,
                                )
                                logger.info(f"Successfully updated name for {cid} to {new_name}")
                    except Exception as api_err:
                        logger.error(f"Failed to fetch info for channel {cid}: {api_err}")
                        continue  # 繼續處理下一個，不要因為一個失敗就中斷整個迴圈

        except Exception as e:
            logger.exception(f"Error during sync_empty_names: {e}")
