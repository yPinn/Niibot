"""Authentication API routes"""

import logging

from asyncpg import Pool
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from core.config import Settings, get_settings
from core.database import get_database_manager
from core.dependencies import (
    _get_token_payload,
    get_auth_service,
    get_channel_service,
    get_current_user_id,
    get_db_pool,
    get_discord_api,
    get_twitch_api,
)
from services import AuthService, DiscordAPIClient, TwitchAPIClient

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
    platform: str  # "twitch" or "discord"
    theme: str  # "dark", "light", or "system"


class LogoutResponse(BaseModel):
    message: str


class PreferencesUpdate(BaseModel):
    theme: str


# ============================================
# Helpers
# ============================================


async def _find_or_create_user(
    pool: Pool,
    platform: str,
    platform_user_id: str,
    username: str,
    display_name: str | None = None,
    avatar: str | None = None,
) -> str:
    """Find existing user by linked account or create a new one. Returns users.id as string."""
    row = await pool.fetchrow(
        "SELECT user_id FROM user_linked_accounts WHERE platform = $1 AND platform_user_id = $2",
        platform,
        platform_user_id,
    )

    if row:
        return str(row["user_id"])

    # Create new user + linked account in a transaction
    async with pool.acquire() as conn:
        async with conn.transaction():
            user_row = await conn.fetchrow(
                "INSERT INTO users (display_name, avatar) VALUES ($1, $2) RETURNING id",
                display_name or username,
                avatar,
            )
            user_id = str(user_row["id"])

            await conn.execute(
                "INSERT INTO user_linked_accounts (user_id, platform, platform_user_id, username) "
                "VALUES ($1, $2, $3, $4)",
                user_row["id"],
                platform,
                platform_user_id,
                username,
            )

    logger.info(f"Created user {user_id} for {platform}:{platform_user_id} ({username})")
    return user_id


# ============================================
# Endpoints
# ============================================


@router.get("/auth/twitch/oauth", response_model=OAuthURLResponse)
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


@router.get("/auth/twitch/callback")
async def twitch_oauth_callback(
    code: str | None = None,
    error: str | None = None,
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Handle Twitch OAuth callback"""
    if error:
        logger.error(f"OAuth error from Twitch: {error}")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error={error}")

    if not code:
        logger.error("No OAuth code received from Twitch")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error=no_code")

    # Check DB readiness (don't use Depends — must redirect, not 503)
    db_manager = get_database_manager()
    if db_manager._pool is None:
        logger.error("Database not ready during OAuth callback")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error=db_not_ready")

    success, error_msg, token_data = await twitch_api.exchange_code_for_token(code)
    if not success or not token_data:
        logger.error(f"Failed to exchange code: {error_msg}")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error={error_msg}")

    platform_user_id = token_data["user_id"]
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")

    user_info = await twitch_api.get_user_info(platform_user_id)
    username = user_info.get("name") or user_info.get("display_name") or platform_user_id

    channel_svc = get_channel_service(db_manager._pool)
    save_success = await channel_svc.save_token(
        user_id=platform_user_id,
        access_token=access_token,
        refresh_token=refresh_token,
        username=username,
    )

    if not save_success:
        logger.error(f"Failed to save token and channel for {username}")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error=save_token_failed")

    # Find or create unified user
    user_id = await _find_or_create_user(
        db_manager._pool,
        "twitch",
        platform_user_id,
        username,
        display_name=user_info.get("display_name"),
        avatar=user_info.get("avatar"),
    )

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
        secure=settings.is_production,
        samesite="strict" if settings.is_production else "lax",
        max_age=30 * 24 * 60 * 60,
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
    payload = _get_token_payload(auth_token)
    user_id = str(payload["sub"])
    platform = payload["platform"]
    platform_user_id = str(payload["platform_user_id"])

    # Get theme from users table
    user_row = await pool.fetchrow("SELECT theme FROM users WHERE id = $1::uuid", user_id)
    theme = user_row["theme"] if user_row else "system"

    if platform == "discord":
        channel_svc = get_channel_service(pool)
        user_info = await channel_svc.get_discord_user(platform_user_id)

        if not user_info:
            raise HTTPException(status_code=404, detail="Discord user not found")

        return UserInfoResponse(**user_info, platform="discord", theme=theme)

    # Twitch user
    user_info = await twitch_api.get_user_info(platform_user_id)

    if not user_info:
        raise HTTPException(status_code=404, detail="User not found")

    return UserInfoResponse(**user_info, platform="twitch", theme=theme)


@router.post("/auth/logout", response_model=LogoutResponse)
async def logout(
    response: Response,
    auth_token: str | None = Cookie(None),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    settings: Settings = Depends(get_settings),
    pool: Pool = Depends(get_db_pool),
) -> LogoutResponse:
    """Logout current user by clearing auth cookie"""
    payload = _get_token_payload(auth_token)
    platform = payload["platform"]
    platform_user_id = str(payload["platform_user_id"])

    if platform == "discord":
        channel_svc = get_channel_service(pool)
        user_info = await channel_svc.get_discord_user(platform_user_id)
        username = user_info.get("name", platform_user_id) if user_info else platform_user_id
    else:
        user_info = await twitch_api.get_user_info(platform_user_id)
        username = user_info.get("name", platform_user_id) if user_info else platform_user_id

    response.delete_cookie(
        key="auth_token",
        path="/",
        httponly=True,
        secure=settings.is_production,
        samesite="strict" if settings.is_production else "lax",
    )
    logger.info(f"User logged out: {username} ({platform}:{platform_user_id})")
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
    if body.theme not in ("dark", "light", "system"):
        raise HTTPException(status_code=400, detail="Invalid theme value")

    await pool.execute(
        "UPDATE users SET theme = $1 WHERE id = $2::uuid",
        body.theme,
        user_id,
    )
    return {"theme": body.theme}


# ============================================
# Discord OAuth Endpoints
# ============================================


class DiscordOAuthStatusResponse(BaseModel):
    enabled: bool
    message: str


@router.get("/auth/discord/status", response_model=DiscordOAuthStatusResponse)
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


@router.get("/auth/discord/oauth", response_model=OAuthURLResponse)
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


@router.get("/auth/discord/callback")
async def discord_oauth_callback(
    code: str | None = None,
    error: str | None = None,
    discord_api: DiscordAPIClient = Depends(get_discord_api),
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Handle Discord OAuth callback"""
    if error:
        logger.error(f"OAuth error from Discord: {error}")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error={error}")

    if not code:
        logger.error("No OAuth code received from Discord")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error=no_code")

    if not discord_api.is_configured:
        logger.error("Discord OAuth not configured")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error=discord_not_configured")

    db_manager = get_database_manager()
    if db_manager._pool is None:
        logger.error("Database not ready during Discord OAuth callback")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error=db_not_ready")

    success, error_msg, token_data = await discord_api.exchange_code_for_token(code)
    if not success or not token_data:
        logger.error(f"Failed to exchange code: {error_msg}")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error={error_msg}")

    platform_user_id = token_data["user_id"]
    username = token_data.get("username", platform_user_id)
    display_name = token_data.get("global_name") or token_data.get("username", username)
    avatar = token_data.get("avatar")

    channel_svc = get_channel_service(db_manager._pool)
    await channel_svc.save_discord_user(platform_user_id, username, display_name, avatar)

    # Find or create unified user
    user_id = await _find_or_create_user(
        db_manager._pool,
        "discord",
        platform_user_id,
        username,
        display_name=display_name,
        avatar=avatar,
    )

    jwt_token = auth_service.create_access_token(
        user_id=user_id,
        platform="discord",
        platform_user_id=platform_user_id,
    )

    response = RedirectResponse(url=f"{settings.frontend_url}/discord/dashboard")
    response.set_cookie(
        key="auth_token",
        value=jwt_token,
        httponly=True,
        secure=settings.is_production,
        samesite="strict" if settings.is_production else "lax",
        max_age=30 * 24 * 60 * 60,
    )

    logger.info(f"Discord user logged in: {username} ({platform_user_id})")
    return response
