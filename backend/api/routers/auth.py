"""認證相關的 API 路由

此層只負責處理 HTTP 請求/響應，業務邏輯在 services 層
"""

import logging

from fastapi import APIRouter, Cookie, Response
from fastapi.responses import RedirectResponse

from config import API_URL, CLIENT_ID, FRONTEND_URL
from services import auth as auth_service
from services import twitch as twitch_service
from services import user as user_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["authentication"])


@router.get("/twitch/oauth")
async def get_twitch_oauth_url():
    """返回 Twitch OAuth URL"""
    if not CLIENT_ID:
        return {"error": "CLIENT_ID not configured"}, 500

    oauth_url = twitch_service.generate_oauth_url()
    return {
        "oauth_url": oauth_url,
        "redirect_uri": f"{API_URL}/api/auth/twitch/callback"
    }


@router.get("/twitch/callback")
async def twitch_oauth_callback(code: str | None = None, error: str | None = None, scope: str | None = None):
    """處理 Twitch OAuth 回調

    接收 Twitch 的 OAuth code，將其轉發給 TwitchIO bot 的 OAuth endpoint 處理，
    建立 JWT token，然後重定向到前端
    """
    if error:
        logger.error(f"OAuth error from Twitch: {error}")
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error={error}")

    if not code:
        logger.error("No OAuth code received from Twitch")
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=no_code")

    # 將 code 轉發給 bot 處理,並取得 user_id
    success, error_msg, user_id = await twitch_service.forward_oauth_code_to_bot(code, scope)

    if not success:
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error={error_msg}")

    if not user_id:
        logger.error("No user_id returned from OAuth")
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=no_user_id")

    # 建立 JWT token
    token = auth_service.create_access_token(user_id)

    # 設定 HTTP-only cookie 並重定向
    response = RedirectResponse(url=FRONTEND_URL)
    response.set_cookie(
        key="auth_token",
        value=token,
        httponly=True,
        secure=False,  # 開發環境設為 False,生產環境應為 True (HTTPS)
        samesite="lax",
        max_age=7*24*60*60  # 7 days
    )

    logger.info(f"User {user_id} logged in successfully")
    return response


@router.get("/user")
async def get_current_user(auth_token: str | None = Cookie(None)):
    """獲取當前登入的使用者資訊

    返回格式：
    {
        "name": "使用者帳號",
        "display_name": "顯示名稱",
        "avatar": "頭像 URL"
    }
    """
    if not auth_token:
        logger.warning("No auth token provided")
        return {"error": "Not logged in"}, 401

    # 驗證 JWT token
    user_id = auth_service.verify_token(auth_token)

    if not user_id:
        logger.warning("Invalid or expired token")
        return {"error": "Invalid or expired token"}, 401

    # 取得使用者資訊
    user_info = await user_service.get_user_info(user_id)

    if not user_info:
        return {"error": "User not found"}, 404

    return user_info


@router.post("/logout")
async def logout(response: Response):
    """登出"""
    response.delete_cookie("auth_token")
    return {"message": "Logged out successfully"}
