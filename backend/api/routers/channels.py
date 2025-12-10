"""頻道相關的 API 路由

此層負責處理監聽頻道列表的查詢
"""

import logging

from fastapi import APIRouter, Cookie, HTTPException
from services import twitch as twitch_service
from services import auth as auth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channels", tags=["channels"])


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
