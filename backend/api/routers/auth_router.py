"""Authentication API routes"""

import logging
from typing import Literal
from urllib.parse import quote as _url_quote

from asyncpg import Pool
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from core.config import Settings, get_settings
from core.database import get_database_manager
from core.dependencies import (
    get_auth_service,
    get_channel_service,
    get_current_user_id,
    get_db_pool,
    get_token_payload,
    get_twitch_api,
)
from services import AuthService, TwitchAPIClient
from services.oauth_service import (
    decode_oauth_state,
    encode_oauth_state,
    find_or_create_user,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["authentication"])


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
    platform: str
    theme: str
    broadcaster_type: str = ""


class LogoutResponse(BaseModel):
    message: str


class PreferencesUpdate(BaseModel):
    theme: Literal["dark", "light", "system"]


# ============================================
# Endpoints
# ============================================


@router.get("/auth/twitch/oauth", response_model=OAuthURLResponse)
async def get_twitch_oauth_url(
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    settings: Settings = Depends(get_settings),
) -> OAuthURLResponse:
    """Get Twitch OAuth authorization URL."""
    state = encode_oauth_state("login", secret=settings.jwt_secret_key)
    oauth_url = twitch_api.generate_oauth_url(state=state)
    return OAuthURLResponse(
        oauth_url=oauth_url,
        redirect_uri=f"{settings.api_url}/api/auth/twitch/callback",
    )


@router.get("/auth/twitch/callback")
async def twitch_oauth_callback(
    code: str | None = None,
    error: str | None = None,
    state: str | None = None,
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Handle Twitch OAuth callback"""
    error_redirect = f"{settings.frontend_url}/login"

    if error:
        logger.error(f"OAuth error from Twitch: {error}")
        return RedirectResponse(url=f"{error_redirect}?error={_url_quote(error, safe='')}")

    decoded_state = decode_oauth_state(state, secret=settings.jwt_secret_key)
    if decoded_state.get("mode") != "login":
        logger.warning("OAuth callback received invalid or tampered state — rejecting")
        return RedirectResponse(url=f"{error_redirect}?error=invalid_state")

    if not code:
        logger.error("No OAuth code received from Twitch")
        return RedirectResponse(url=f"{error_redirect}?error=no_code")

    # Must redirect on DB error — cannot use Depends(get_db_pool)
    try:
        pool = get_database_manager().pool
    except RuntimeError:
        logger.error("Database not ready during Twitch OAuth callback")
        return RedirectResponse(url=f"{error_redirect}?error=db_not_ready")

    success, error_msg, token_data = await twitch_api.exchange_code_for_token(code)
    if not success or not token_data:
        logger.error(f"Failed to exchange code: {error_msg}")
        return RedirectResponse(
            url=f"{error_redirect}?error={_url_quote(error_msg or 'token_exchange_failed', safe='')}"
        )

    platform_user_id = token_data["user_id"]
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")

    user_info = await twitch_api.get_user_info(platform_user_id)
    username = user_info.get("name") or user_info.get("display_name") or platform_user_id

    try:
        channel_svc = get_channel_service(pool)
        save_success = await channel_svc.save_token(
            user_id=platform_user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            username=username,
        )

        if not save_success:
            logger.error(f"Failed to save token and channel for {username}")
            return RedirectResponse(url=f"{error_redirect}?error=save_token_failed")

        user_id = await find_or_create_user(
            pool,
            "twitch",
            platform_user_id,
            username,
            display_name=user_info.get("display_name"),
            avatar=user_info.get("avatar"),
        )
    except Exception as e:
        logger.error(f"DB error during Twitch OAuth for {username}: {type(e).__name__}: {e}")
        return RedirectResponse(url=f"{error_redirect}?error=db_timeout")

    jwt_token = auth_service.create_access_token(
        user_id=user_id,
        platform="twitch",
        platform_user_id=platform_user_id,
    )

    response = RedirectResponse(url=f"{settings.frontend_url}/dashboard")
    response.set_cookie(
        key="auth_token",
        value=jwt_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.jwt_expire_days * 24 * 60 * 60,
    )

    logger.info(f"User logged in and synced: {username} ({platform_user_id})")
    return response


@router.get("/auth/user", response_model=UserInfoResponse)
async def get_current_user(
    auth_token: str | None = Cookie(None),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    pool: Pool = Depends(get_db_pool),
) -> UserInfoResponse:
    """Get current authenticated user information"""
    payload = get_token_payload(auth_token)
    user_id = str(payload["sub"])
    platform_user_id = str(payload["platform_user_id"])

    theme = "system"
    try:
        user_row = await pool.fetchrow("SELECT theme FROM users WHERE id = $1::uuid", user_id)
        if user_row:
            theme = user_row["theme"]
    except Exception as e:
        logger.warning(f"DB error fetching theme for user {user_id}: {type(e).__name__}: {e}")

    user_info = await twitch_api.get_user_info(platform_user_id)
    if not user_info:
        raise HTTPException(status_code=404, detail="User not found")

    return UserInfoResponse(**user_info, platform="twitch", theme=theme)


@router.post("/auth/logout", response_model=LogoutResponse)
async def logout(
    response: Response,
    auth_token: str | None = Cookie(None),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> LogoutResponse:
    """Logout current user by clearing auth cookie"""
    payload = get_token_payload(auth_token)
    platform_user_id = str(payload["platform_user_id"])

    user_info = await twitch_api.get_user_info(platform_user_id)
    username = user_info.get("name", platform_user_id) if user_info else platform_user_id

    response.delete_cookie(
        key="auth_token",
        path="/",
        httponly=True,
        secure=True,
        samesite="lax",
    )
    logger.info(f"User logged out: {username} (twitch:{platform_user_id})")
    return LogoutResponse(message="Logged out successfully")


# ============================================
# User Preferences
# ============================================


@router.patch("/user/preferences")
async def update_preferences(
    body: PreferencesUpdate,
    user_id: str = Depends(get_current_user_id),
    pool: Pool = Depends(get_db_pool),
) -> dict:
    """Update user preferences (theme, etc.)"""
    await pool.execute(
        "UPDATE users SET theme = $1 WHERE id = $2::uuid",
        body.theme,
        user_id,
    )
    return {"theme": body.theme}
