"""Authentication API routes"""

import logging
from typing import Optional

from core.config import Settings, get_settings
from core.dependencies import (
    get_auth_service,
    get_channel_service,
    get_current_user_id,
    get_db_pool,
    get_twitch_api,
)
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from services import AuthService, ChannelService, TwitchAPIClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["authentication"])


# ============================================
# Response Models
# ============================================


class OAuthURLResponse(BaseModel):
    oauth_url: str
    redirect_uri: str


class UserInfoResponse(BaseModel):
    id: str
    name: str
    display_name: str
    avatar: str


class LogoutResponse(BaseModel):
    message: str


# ============================================
# Endpoints
# ============================================


@router.get("/twitch/oauth", response_model=OAuthURLResponse)
async def get_twitch_oauth_url(
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    settings: Settings = Depends(get_settings),
) -> OAuthURLResponse:
    """Get Twitch OAuth authorization URL"""
    oauth_url = twitch_api.generate_oauth_url()
    return OAuthURLResponse(
        oauth_url=oauth_url,
        redirect_uri=f"{settings.api_url}/api/auth/twitch/callback",
    )


@router.get("/twitch/callback")
async def twitch_oauth_callback(
    code: Optional[str] = None,
    error: Optional[str] = None,
    scope: Optional[str] = None,
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    auth_service: AuthService = Depends(get_auth_service),
    channel_service: ChannelService = Depends(lambda: get_channel_service(get_db_pool())),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Handle Twitch OAuth callback"""
    # Handle OAuth errors
    if error:
        logger.error(f"OAuth error from Twitch: {error}")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error={error}")

    if not code:
        logger.error("No OAuth code received from Twitch")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error=no_code")

    # Exchange code for token
    success, error_msg, token_data = await twitch_api.exchange_code_for_token(code)

    if not success or not token_data:
        logger.error(f"Failed to exchange code: {error_msg}")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error={error_msg}")

    user_id = token_data["user_id"]
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")

    # Save token to database
    pool = await get_db_pool()
    channel_svc = get_channel_service(pool)
    save_success = await channel_svc.save_token(user_id, access_token, refresh_token)

    if not save_success:
        logger.error("Failed to save token to database")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error=save_token_failed")

    # Create JWT token
    jwt_token = auth_service.create_access_token(user_id)

    # Set cookie and redirect
    response = RedirectResponse(url=f"{settings.frontend_url}/dashboard")
    response.set_cookie(
        key="auth_token",
        value=jwt_token,
        httponly=True,
        secure=settings.is_production,
        samesite="strict" if settings.is_production else "lax",
        max_age=30 * 24 * 60 * 60,  # 30 days
    )

    logger.info(f"User logged in: {user_id}")
    return response


@router.get("/user", response_model=UserInfoResponse)
async def get_current_user(
    user_id: str = Depends(get_current_user_id),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> UserInfoResponse:
    """Get current authenticated user information"""
    user_info = await twitch_api.get_user_info(user_id)

    if not user_info:
        raise HTTPException(status_code=404, detail="User not found")

    return UserInfoResponse(**user_info)


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    response: Response,
    user_id: str = Depends(get_current_user_id),
    settings: Settings = Depends(get_settings),
) -> LogoutResponse:
    """Logout current user by clearing auth cookie"""
    response.delete_cookie(
        key="auth_token",
        path="/",
        httponly=True,
        secure=settings.is_production,
        samesite="strict" if settings.is_production else "lax",
    )
    logger.info(f"User logged out: {user_id}")
    return LogoutResponse(message="Logged out successfully")
