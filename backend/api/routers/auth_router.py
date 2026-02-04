"""Authentication API routes"""

import logging

from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from core.config import Settings, get_settings
from core.dependencies import (
    get_auth_service,
    get_channel_service,
    get_current_user_id,
    get_db_pool,
    get_discord_api,
    get_twitch_api,
)
from services import AuthService, DiscordAPIClient, TwitchAPIClient

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
    platform: str  # "twitch" or "discord"


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
    code: str | None = None,
    error: str | None = None,
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    auth_service: AuthService = Depends(get_auth_service),
    pool: Pool = Depends(get_db_pool),
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
    pool = get_db_pool()
    channel_svc = get_channel_service(pool)
    save_success = await channel_svc.save_token(user_id, access_token, refresh_token)

    if not save_success:
        logger.error("Failed to save token to database")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error=save_token_failed")

    # Create JWT token
    jwt_token = auth_service.create_access_token(user_id)

    # Fetch user info for logging
    user_info = await twitch_api.get_user_info(user_id)
    username = user_info.get("name", user_id) if user_info else user_id

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

    logger.info(f"User logged in: {username} ({user_id})")
    return response


@router.get("/user", response_model=UserInfoResponse)
async def get_current_user(
    user_id: str = Depends(get_current_user_id),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    pool: Pool = Depends(get_db_pool),
) -> UserInfoResponse:
    """Get current authenticated user information"""
    # Check if this is a Discord user (has discord: prefix)
    if user_id.startswith("discord:"):
        discord_user_id = user_id.replace("discord:", "")
        pool = get_db_pool()
        channel_svc = get_channel_service(pool)
        user_info = await channel_svc.get_discord_user(discord_user_id)

        if not user_info:
            raise HTTPException(status_code=404, detail="Discord user not found")

        return UserInfoResponse(**user_info, platform="discord")

    # Twitch user
    user_info = await twitch_api.get_user_info(user_id)

    if not user_info:
        raise HTTPException(status_code=404, detail="User not found")

    return UserInfoResponse(**user_info, platform="twitch")


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    response: Response,
    user_id: str = Depends(get_current_user_id),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    settings: Settings = Depends(get_settings),
    pool: Pool = Depends(get_db_pool),
) -> LogoutResponse:
    """Logout current user by clearing auth cookie"""
    # Fetch user info for logging
    if user_id.startswith("discord:"):
        discord_user_id = user_id.replace("discord:", "")
        pool = get_db_pool()
        channel_svc = get_channel_service(pool)
        user_info = await channel_svc.get_discord_user(discord_user_id)
        username = user_info.get("name", discord_user_id) if user_info else discord_user_id
    else:
        user_info = await twitch_api.get_user_info(user_id)
        username = user_info.get("name", user_id) if user_info else user_id

    response.delete_cookie(
        key="auth_token",
        path="/",
        httponly=True,
        secure=settings.is_production,
        samesite="strict" if settings.is_production else "lax",
    )
    logger.info(f"User logged out: {username} ({user_id})")
    return LogoutResponse(message="Logged out successfully")


# ============================================
# Discord OAuth Endpoints
# ============================================


class DiscordOAuthStatusResponse(BaseModel):
    enabled: bool
    message: str


@router.get("/discord/status", response_model=DiscordOAuthStatusResponse)
async def get_discord_oauth_status(
    discord_api: DiscordAPIClient = Depends(get_discord_api),
) -> DiscordOAuthStatusResponse:
    """Check if Discord OAuth is configured and available"""
    if discord_api.is_configured:
        return DiscordOAuthStatusResponse(
            enabled=True,
            message="Discord OAuth is available",
        )
    return DiscordOAuthStatusResponse(
        enabled=False,
        message="Discord OAuth is not configured",
    )


@router.get("/discord/oauth", response_model=OAuthURLResponse)
async def get_discord_oauth_url(
    discord_api: DiscordAPIClient = Depends(get_discord_api),
    settings: Settings = Depends(get_settings),
) -> OAuthURLResponse:
    """Get Discord OAuth authorization URL"""
    if not discord_api.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Discord OAuth is not configured",
        )

    oauth_url = discord_api.generate_oauth_url()
    return OAuthURLResponse(
        oauth_url=oauth_url,
        redirect_uri=f"{settings.api_url}/api/auth/discord/callback",
    )


@router.get("/discord/callback")
async def discord_oauth_callback(
    code: str | None = None,
    error: str | None = None,
    discord_api: DiscordAPIClient = Depends(get_discord_api),
    auth_service: AuthService = Depends(get_auth_service),
    pool: Pool = Depends(get_db_pool),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Handle Discord OAuth callback"""
    # Handle OAuth errors
    if error:
        logger.error(f"OAuth error from Discord: {error}")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error={error}")

    if not code:
        logger.error("No OAuth code received from Discord")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error=no_code")

    if not discord_api.is_configured:
        logger.error("Discord OAuth not configured")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error=discord_not_configured")

    # Exchange code for token
    success, error_msg, token_data = await discord_api.exchange_code_for_token(code)

    if not success or not token_data:
        logger.error(f"Failed to exchange code: {error_msg}")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error={error_msg}")

    user_id = token_data["user_id"]
    username = token_data.get("username", user_id)
    display_name = token_data.get("global_name") or token_data.get("username", username)
    avatar = token_data.get("avatar")

    # Save Discord user info to database (required since Discord OAuth can't fetch by ID)
    pool = get_db_pool()
    channel_svc = get_channel_service(pool)
    await channel_svc.save_discord_user(user_id, username, display_name, avatar)

    # Create JWT token with discord: prefix to distinguish from Twitch users
    jwt_token = auth_service.create_access_token(f"discord:{user_id}")

    # Set cookie and redirect to Discord dashboard
    response = RedirectResponse(url=f"{settings.frontend_url}/discord/dashboard")
    response.set_cookie(
        key="auth_token",
        value=jwt_token,
        httponly=True,
        secure=settings.is_production,
        samesite="strict" if settings.is_production else "lax",
        max_age=30 * 24 * 60 * 60,  # 30 days
    )

    logger.info(f"Discord user logged in: {username} ({user_id})")
    return response
