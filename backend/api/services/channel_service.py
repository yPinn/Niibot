"""Channel management service"""

import logging
from typing import Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)


class ChannelService:
    """Handle channel-related database operations"""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_channel_status(self, user_id: str) -> Dict:
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

    async def get_enabled_channels(self) -> List[Dict]:
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

    async def get_user_token(self, user_id: str) -> Optional[str]:
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

    async def save_token(self, user_id: str, access_token: str, refresh_token: str) -> bool:
        """Save or update user's OAuth token"""
        try:
            async with self.pool.acquire() as conn:
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

            logger.debug(f"Token saved for user: {user_id}")
            return True

        except Exception as e:
            logger.exception(f"Error saving token to database: {e}")
            return False
