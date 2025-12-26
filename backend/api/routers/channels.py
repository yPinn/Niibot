"""頻道相關的 API 路由

此層負責處理監聽頻道列表的查詢
"""

import logging

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel
from services import auth as auth_service
from services import channel as channel_service
from services import twitch as twitch_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channels", tags=["channels"])


class ChannelToggleRequest(BaseModel):
    """啟用/停用頻道的請求體"""
    channel_id: str
    enabled: bool


@router.get("/monitored")
async def get_monitored_channels(auth_token: str | None = Cookie(None)):
    """獲取監聽的頻道列表

    返回格式：
    [
        {
            "id": "頻道 ID",
            "name": "頻道帳號",
            "display_name": "顯示名稱",
            "avatar": "頭像 URL",
            "is_live": true/false,
            "viewer_count": 觀看人數（如果在線）,
            "game_name": "遊戲名稱"（如果在線）
        }
    ]
    """
    if not auth_token:
        logger.warning("No auth token provided")
        raise HTTPException(status_code=401, detail="Not logged in")

    # 驗證 JWT token
    user_id = auth_service.verify_token(auth_token)

    if not user_id:
        logger.warning("Invalid or expired token")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # 獲取監聽的頻道列表
    try:
        channels = await twitch_service.get_monitored_channels(user_id)
        return channels
    except Exception as e:
        logger.error(f"Failed to get monitored channels: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch channels")


@router.get("/my-status")
async def get_my_channel_status(auth_token: str | None = Cookie(None)):
    """獲取當前使用者的頻道訂閱狀態

    返回格式：
    {
        "subscribed": true/false,
        "channel_id": "頻道 ID",
        "channel_name": "頻道名稱"
    }
    """
    if not auth_token:
        logger.warning("No auth token provided")
        raise HTTPException(status_code=401, detail="Not logged in")

    # 驗證 JWT token
    user_id = auth_service.verify_token(auth_token)

    if not user_id:
        logger.warning("Invalid or expired token")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # 檢查當前使用者的頻道是否被訂閱
    try:
        status = await channel_service.get_my_channel_status(user_id)
        return status
    except Exception as e:
        logger.error(f"Failed to get my channel status: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch status")


@router.post("/toggle")
async def toggle_channel(
    request: ChannelToggleRequest,
    auth_token: str | None = Cookie(None)
):
    """啟用或停用頻道監聽

    請求體：
    {
        "channel_id": "頻道 ID",
        "enabled": true/false
    }
    """
    if not auth_token:
        logger.warning("No auth token provided")
        raise HTTPException(status_code=401, detail="Not logged in")

    # 驗證 JWT token
    user_id = auth_service.verify_token(auth_token)

    if not user_id:
        logger.warning("Invalid or expired token")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # 更新頻道狀態
    try:
        success = await channel_service.toggle_channel(
            request.channel_id,
            request.enabled
        )

        if success:
            action = "enabled" if request.enabled else "disabled"
            logger.info(f"Channel {request.channel_id} {action} by user {user_id}")
            return {"message": f"Channel {action} successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to update channel status")

    except Exception as e:
        logger.exception(f"Failed to toggle channel: {e}")
        raise HTTPException(status_code=500, detail=str(e))
