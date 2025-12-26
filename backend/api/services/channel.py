"""頻道管理相關的業務邏輯"""

import logging

logger = logging.getLogger(__name__)


async def get_my_channel_status(user_id: str) -> dict:
    """獲取當前使用者的頻道訂閱狀態

    Args:
        user_id: Twitch user ID

    Returns:
        dict: {
            "subscribed": bool,
            "channel_id": str,
            "channel_name": str
        }
    """
    try:
        from services.database import get_database_pool

        pool = await get_database_pool()
        async with pool.acquire() as connection:
            # 檢查 channels 表中是否有該用戶的頻道且 enabled = true
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
    """啟用或停用頻道監聽

    Args:
        channel_id: 頻道 ID (Twitch user_id)
        enabled: True 為啟用，False 為停用

    Returns:
        bool: 是否成功
    """
    try:

        from services.database import get_database_pool

        pool = await get_database_pool()
        async with pool.acquire() as connection:
            # 更新資料庫
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
