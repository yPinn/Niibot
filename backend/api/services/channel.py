"""Channel management service"""

import logging

logger = logging.getLogger(__name__)


async def get_my_channel_status(user_id: str) -> dict:
    try:
        from services.database import get_database_pool

        pool = await get_database_pool()
        async with pool.acquire() as connection:
            channel_row = await connection.fetchrow(
                """
                SELECT channel_id, channel_name, enabled
                FROM channels
                WHERE channel_id = $1
                """,
                user_id
            )

            if channel_row and channel_row["enabled"]:
                return {
                    "subscribed": True,
                    "channel_id": channel_row["channel_id"],
                    "channel_name": channel_row["channel_name"]
                }
            else:
                return {
                    "subscribed": False,
                    "channel_id": user_id,
                    "channel_name": channel_row["channel_name"] if channel_row else ""
                }

    except Exception as e:
        logger.exception(f"Error getting channel status for user {user_id}: {e}")
        return {
            "subscribed": False,
            "channel_id": user_id,
            "channel_name": ""
        }


async def toggle_channel(channel_id: str, enabled: bool) -> bool:
    try:
        from services.database import get_database_pool

        pool = await get_database_pool()
        async with pool.acquire() as connection:
            await connection.execute(
                """
                UPDATE channels
                SET enabled = $1, updated_at = CURRENT_TIMESTAMP
                WHERE channel_id = $2
                """,
                enabled,
                channel_id
            )

        logger.info(f"Channel {channel_id} {'enabled' if enabled else 'disabled'}")
        return True

    except Exception as e:
        logger.exception(f"Error toggling channel {channel_id}: {e}")
        return False
