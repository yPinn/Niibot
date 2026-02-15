"""Authentication API routes"""

import base64
import json
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


def _encode_oauth_state(mode: str, user_id: str | None = None) -> str:
    """Encode OAuth state as base64 JSON."""
    data: dict = {"mode": mode}
    if user_id:
        data["uid"] = user_id
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


def _decode_oauth_state(state: str | None) -> dict:
    """Decode OAuth state from base64 JSON. Returns {"mode": "login"} on failure."""
    if not state:
        return {"mode": "login"}
    try:
        return json.loads(base64.urlsafe_b64decode(state.encode()).decode())
    except Exception:
        return {"mode": "login"}


async def _link_account(
    pool: Pool,
    user_id: str,
    platform: str,
    platform_user_id: str,
    username: str,
) -> tuple[bool, str | None]:
    """Link a platform account to an existing user.

    Returns (success, error_code).
    """
    # Check if this platform account is already linked
    row = await pool.fetchrow(
        "SELECT user_id FROM user_linked_accounts WHERE platform = $1 AND platform_user_id = $2",
        platform,
        platform_user_id,
    )
    if row:
        existing_uid = str(row["user_id"])
        if existing_uid == user_id:
            return True, None  # Already linked to this user — idempotent
        return False, "already_linked"

    # Check if user already has an account for this platform
    row = await pool.fetchrow(
        "SELECT platform_user_id FROM user_linked_accounts WHERE user_id = $1::uuid AND platform = $2",
        user_id,
        platform,
    )
    if row:
        return False, "platform_already_linked"

    # Link the account
    await pool.execute(
        "INSERT INTO user_linked_accounts (user_id, platform, platform_user_id, username) "
        "VALUES ($1::uuid, $2, $3, $4)",
        user_id,
        platform,
        platform_user_id,
        username,
    )
    logger.info(f"Linked {platform}:{platform_user_id} ({username}) to user {user_id}")
    return True, None


# ============================================
# Endpoints
# ============================================


@router.get("/auth/twitch/oauth", response_model=OAuthURLResponse)
async def get_twitch_oauth_url(
    mode: str = "login",
    auth_token: str | None = Cookie(None),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    settings: Settings = Depends(get_settings),
) -> OAuthURLResponse:
    """Get Twitch OAuth authorization URL. Use mode=link to link account."""
    state = None
    if mode == "link":
        payload = _get_token_payload(auth_token)
        state = _encode_oauth_state("link", user_id=str(payload["sub"]))

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
    auth_token: str | None = Cookie(None),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Handle Twitch OAuth callback"""
    state_data = _decode_oauth_state(state)
    is_link_mode = state_data.get("mode") == "link"
    error_redirect = (
        f"{settings.frontend_url}/settings" if is_link_mode else f"{settings.frontend_url}/login"
    )

    if error:
        logger.error(f"OAuth error from Twitch: {error}")
        return RedirectResponse(url=f"{error_redirect}?error={error}")

    if not code:
        logger.error("No OAuth code received from Twitch")
        return RedirectResponse(url=f"{error_redirect}?error=no_code")

    # Check DB readiness (don't use Depends — must redirect, not 503)
    db_manager = get_database_manager()
    if db_manager._pool is None:
        logger.error("Database not ready during OAuth callback")
        return RedirectResponse(url=f"{error_redirect}?error=db_not_ready")

    success, error_msg, token_data = await twitch_api.exchange_code_for_token(code)
    if not success or not token_data:
        logger.error(f"Failed to exchange code: {error_msg}")
        return RedirectResponse(url=f"{error_redirect}?error={error_msg}")

    platform_user_id = token_data["user_id"]
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")

    user_info = await twitch_api.get_user_info(platform_user_id)
    username = user_info.get("name") or user_info.get("display_name") or platform_user_id

    try:
        channel_svc = get_channel_service(db_manager._pool)
        save_success = await channel_svc.save_token(
            user_id=platform_user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            username=username,
        )

        if not save_success:
            logger.error(f"Failed to save token and channel for {username}")
            return RedirectResponse(url=f"{error_redirect}?error=save_token_failed")

        # Link mode: attach to existing user
        if is_link_mode:
            link_user_id = state_data.get("uid")
            if not link_user_id:
                return RedirectResponse(url=f"{error_redirect}?error=invalid_state")

            # Verify cookie user matches state user (prevent session swap)
            try:
                payload = _get_token_payload(auth_token)
                if str(payload["sub"]) != link_user_id:
                    logger.warning(
                        f"Link uid mismatch: cookie={payload['sub']}, state={link_user_id}"
                    )
                    return RedirectResponse(url=f"{error_redirect}?error=session_mismatch")
            except HTTPException:
                return RedirectResponse(url=f"{error_redirect}?error=not_authenticated")

            link_ok, link_err = await _link_account(
                db_manager._pool, link_user_id, "twitch", platform_user_id, username
            )
            if not link_ok:
                return RedirectResponse(url=f"{settings.frontend_url}/settings?error={link_err}")

            logger.info(f"Linked Twitch {username} ({platform_user_id}) to user {link_user_id}")
            return RedirectResponse(url=f"{settings.frontend_url}/settings?linked=twitch")

        # Login mode: find or create unified user
        user_id = await _find_or_create_user(
            db_manager._pool,
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
        samesite="none",
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

    # Get theme from users table (non-critical — default to "system" on DB error)
    theme = "system"
    try:
        user_row = await pool.fetchrow("SELECT theme FROM users WHERE id = $1::uuid", user_id)
        if user_row:
            theme = user_row["theme"]
    except Exception as e:
        logger.warning(f"DB error fetching theme for user {user_id}: {type(e).__name__}: {e}")

    if platform == "discord":
        try:
            channel_svc = get_channel_service(pool)
            user_info = await channel_svc.get_discord_user(platform_user_id)
        except Exception as e:
            logger.warning(
                f"DB error fetching Discord user {platform_user_id}: {type(e).__name__}: {e}"
            )
            user_info = None

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
        secure=True,
        samesite="none",
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
    mode: str = "login",
    auth_token: str | None = Cookie(None),
    discord_api: DiscordAPIClient = Depends(get_discord_api),
    settings: Settings = Depends(get_settings),
) -> OAuthURLResponse:
    """Get Discord OAuth authorization URL. Use mode=link to link account."""
    if not discord_api.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Discord OAuth is not configured",
        )

    state = None
    if mode == "link":
        payload = _get_token_payload(auth_token)
        state = _encode_oauth_state("link", user_id=str(payload["sub"]))

    oauth_url = discord_api.generate_oauth_url(state=state)
    return OAuthURLResponse(
        oauth_url=oauth_url,
        redirect_uri=f"{settings.api_url}/api/auth/discord/callback",
    )


@router.get("/auth/discord/callback")
async def discord_oauth_callback(
    code: str | None = None,
    error: str | None = None,
    state: str | None = None,
    auth_token: str | None = Cookie(None),
    discord_api: DiscordAPIClient = Depends(get_discord_api),
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Handle Discord OAuth callback"""
    state_data = _decode_oauth_state(state)
    is_link_mode = state_data.get("mode") == "link"
    error_redirect = (
        f"{settings.frontend_url}/settings" if is_link_mode else f"{settings.frontend_url}/login"
    )

    if error:
        logger.error(f"OAuth error from Discord: {error}")
        return RedirectResponse(url=f"{error_redirect}?error={error}")

    if not code:
        logger.error("No OAuth code received from Discord")
        return RedirectResponse(url=f"{error_redirect}?error=no_code")

    if not discord_api.is_configured:
        logger.error("Discord OAuth not configured")
        return RedirectResponse(url=f"{error_redirect}?error=discord_not_configured")

    db_manager = get_database_manager()
    if db_manager._pool is None:
        logger.error("Database not ready during Discord OAuth callback")
        return RedirectResponse(url=f"{error_redirect}?error=db_not_ready")

    success, error_msg, token_data = await discord_api.exchange_code_for_token(code)
    if not success or not token_data:
        logger.error(f"Failed to exchange code: {error_msg}")
        return RedirectResponse(url=f"{error_redirect}?error={error_msg}")

    platform_user_id = token_data["user_id"]
    username = token_data.get("username", platform_user_id)
    display_name = token_data.get("global_name") or token_data.get("username", username)
    avatar = token_data.get("avatar")

    try:
        channel_svc = get_channel_service(db_manager._pool)
        await channel_svc.save_discord_user(platform_user_id, username, display_name, avatar)

        # Link mode: attach to existing user
        if is_link_mode:
            link_user_id = state_data.get("uid")
            if not link_user_id:
                return RedirectResponse(url=f"{error_redirect}?error=invalid_state")

            # Verify cookie user matches state user (prevent session swap)
            try:
                payload = _get_token_payload(auth_token)
                if str(payload["sub"]) != link_user_id:
                    logger.warning(
                        f"Link uid mismatch: cookie={payload['sub']}, state={link_user_id}"
                    )
                    return RedirectResponse(url=f"{error_redirect}?error=session_mismatch")
            except HTTPException:
                return RedirectResponse(url=f"{error_redirect}?error=not_authenticated")

            link_ok, link_err = await _link_account(
                db_manager._pool, link_user_id, "discord", platform_user_id, username
            )
            if not link_ok:
                return RedirectResponse(url=f"{settings.frontend_url}/settings?error={link_err}")

            logger.info(f"Linked Discord {username} ({platform_user_id}) to user {link_user_id}")
            return RedirectResponse(url=f"{settings.frontend_url}/settings?linked=discord")

        # Login mode: find or create unified user
        user_id = await _find_or_create_user(
            db_manager._pool,
            "discord",
            platform_user_id,
            username,
            display_name=display_name,
            avatar=avatar,
        )
    except Exception as e:
        logger.error(f"DB error during Discord OAuth for {username}: {type(e).__name__}: {e}")
        return RedirectResponse(url=f"{error_redirect}?error=db_timeout")

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
        secure=True,
        samesite="none",
        max_age=30 * 24 * 60 * 60,
    )

    logger.info(f"Discord user logged in: {username} ({platform_user_id})")
    return response


# ============================================
# Linked Accounts
# ============================================


class LinkedAccountInfo(BaseModel):
    platform: str
    platform_user_id: str
    username: str
    created_at: str


@router.get("/user/linked-accounts")
async def get_linked_accounts(
    user_id: str = Depends(get_current_user_id),
    pool: Pool = Depends(get_db_pool),
) -> list[LinkedAccountInfo]:
    """Get all linked accounts for the current user."""
    rows = await pool.fetch(
        "SELECT platform, platform_user_id, username, created_at "
        "FROM user_linked_accounts WHERE user_id = $1::uuid ORDER BY created_at ASC",
        user_id,
    )
    return [
        LinkedAccountInfo(
            platform=row["platform"],
            platform_user_id=row["platform_user_id"],
            username=row["username"] or "",
            created_at=row["created_at"].isoformat(),
        )
        for row in rows
    ]


@router.delete("/user/linked-accounts/{platform}")
async def unlink_account(
    platform: str,
    user_id: str = Depends(get_current_user_id),
    auth_token: str | None = Cookie(None),
    pool: Pool = Depends(get_db_pool),
) -> dict:
    """Unlink a platform account from the current user."""
    if platform not in ("twitch", "discord"):
        raise HTTPException(status_code=400, detail="Invalid platform")

    # Cannot unlink the platform used for current session
    payload = _get_token_payload(auth_token)
    if payload["platform"] == platform:
        raise HTTPException(status_code=400, detail="Cannot unlink your current session platform")

    # Must keep at least one linked account
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM user_linked_accounts WHERE user_id = $1::uuid",
        user_id,
    )
    if count <= 1:
        raise HTTPException(status_code=400, detail="Cannot unlink your last account")

    result = await pool.execute(
        "DELETE FROM user_linked_accounts WHERE user_id = $1::uuid AND platform = $2",
        user_id,
        platform,
    )

    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Account not found")

    logger.info(f"User {user_id} unlinked {platform} account")
    return {"message": f"{platform} account unlinked"}
