"""Authentication API routes"""

import logging
import time
from collections import defaultdict
from typing import Literal
from urllib.parse import quote as _url_quote

from asyncpg import Pool
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

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
from shared.repositories.activation_code import ActivationCodeRepository
from shared.repositories.activation_request import ActivationRequestRepository

LOGGER: logging.Logger = logging.getLogger(__name__)


class _OTPRateLimiter:
    """Per-user OTP attempt limiter: max 5 attempts per 10-minute window (in-process)."""

    _MAX_ATTEMPTS = 5
    _WINDOW = 600.0  # seconds

    def __init__(self) -> None:
        self._attempts: dict[str, list[float]] = defaultdict(list)

    def check_and_record(self, user_id: str) -> bool:
        """Returns True if the attempt is allowed, False if rate-limited."""
        now = time.monotonic()
        cutoff = now - self._WINDOW
        self._attempts[user_id] = [t for t in self._attempts[user_id] if t > cutoff]
        if len(self._attempts[user_id]) >= self._MAX_ATTEMPTS:
            return False
        self._attempts[user_id].append(now)
        return True


_otp_rate_limiter = _OTPRateLimiter()

router = APIRouter(prefix="/api", tags=["authentication"])


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
    is_activated: bool = False
    is_owner: bool = False


class ActivateRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class ActivationRequestCreate(BaseModel):
    note: str = Field(default="", max_length=300)


class LogoutResponse(BaseModel):
    message: str


class PreferencesUpdate(BaseModel):
    theme: Literal["dark", "light", "system"]


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
        LOGGER.error(f"OAuth error from Twitch: {error}")
        return RedirectResponse(url=f"{error_redirect}?error={_url_quote(error, safe='')}")

    decoded_state = decode_oauth_state(state, secret=settings.jwt_secret_key)
    if decoded_state.get("mode") != "login":
        LOGGER.warning("OAuth callback received invalid or tampered state — rejecting")
        return RedirectResponse(url=f"{error_redirect}?error=invalid_state")

    if not code:
        LOGGER.error("No OAuth code received from Twitch")
        return RedirectResponse(url=f"{error_redirect}?error=no_code")

    # Must redirect on DB error — cannot use Depends(get_db_pool)
    try:
        pool = get_database_manager().pool
    except RuntimeError:
        LOGGER.error("Database not ready during Twitch OAuth callback")
        return RedirectResponse(url=f"{error_redirect}?error=db_not_ready")

    success, error_msg, token_data = await twitch_api.exchange_code_for_token(code)
    if not success or not token_data:
        LOGGER.error(f"Failed to exchange code: {error_msg}")
        return RedirectResponse(
            url=f"{error_redirect}?error={_url_quote(error_msg or 'token_exchange_failed', safe='')}"
        )

    platform_user_id = token_data["user_id"]
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")
    scopes = token_data.get("scopes")

    user_info = await twitch_api.get_user_info(platform_user_id)
    username = user_info.get("name") or user_info.get("display_name") or platform_user_id

    try:
        channel_svc = get_channel_service(pool)
        save_success = await channel_svc.save_token(
            user_id=platform_user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            username=username,
            scopes=scopes,
            display_name=user_info.get("display_name"),
        )

        if not save_success:
            LOGGER.error(f"Failed to save token and channel for {username}")
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
        LOGGER.error(f"DB error during Twitch OAuth for {username}: {type(e).__name__}: {e}")
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

    LOGGER.info(f"User logged in and synced: {username} ({platform_user_id})")
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
    is_activated = False
    try:
        user_row = await pool.fetchrow(
            "SELECT theme, is_activated FROM users WHERE id = $1::uuid", user_id
        )
        if user_row:
            theme = user_row["theme"]
            is_activated = user_row["is_activated"]
    except Exception as e:
        LOGGER.warning(f"DB error fetching user row for {user_id}: {type(e).__name__}: {e}")

    user_info = await twitch_api.get_user_info(platform_user_id)
    if not user_info:
        raise HTTPException(status_code=404, detail="User not found")

    owner_id_cfg = str(get_settings().owner_id)
    is_owner = platform_user_id == owner_id_cfg
    if not is_owner:
        LOGGER.debug(
            f"is_owner=False: platform_user_id={platform_user_id!r} owner_id={owner_id_cfg!r}"
        )
    return UserInfoResponse(
        **user_info, platform="twitch", theme=theme, is_activated=is_activated, is_owner=is_owner
    )


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
    LOGGER.info(f"User logged out: {username} (twitch:{platform_user_id})")
    return LogoutResponse(message="Logged out successfully")


@router.get("/auth/pending-code")
async def get_pending_code(
    auth_token: str | None = Cookie(None),
    pool: Pool = Depends(get_db_pool),
) -> dict:
    """Return the pending activation code for the current user, if one exists."""
    payload = get_token_payload(auth_token)
    platform = str(payload["platform"])
    platform_user_id = str(payload["platform_user_id"])

    repo = ActivationCodeRepository(pool)
    code = await repo.get_plain_code(platform, platform_user_id)
    return {"code": code}


@router.post("/auth/activate")
async def activate_account(
    body: ActivateRequest,
    auth_token: str | None = Cookie(None),
    pool: Pool = Depends(get_db_pool),
) -> dict:
    """Activate account using an OTP code from the niibot_auth redemption."""
    payload = get_token_payload(auth_token)
    user_id = str(payload["sub"])
    platform = str(payload["platform"])
    platform_user_id = str(payload["platform_user_id"])

    already_activated = await pool.fetchval(
        "SELECT is_activated FROM users WHERE id = $1::uuid", user_id
    )
    if already_activated:
        return {"activated": True}

    if not _otp_rate_limiter.check_and_record(user_id):
        raise HTTPException(status_code=429, detail="too_many_attempts")

    repo = ActivationCodeRepository(pool)
    success = await repo.redeem(
        code=body.code.strip(),
        platform=platform,
        platform_user_id=platform_user_id,
        user_id=user_id,
    )

    if not success:
        raise HTTPException(status_code=400, detail="invalid_or_expired_code")

    LOGGER.info(f"Account activated: user {user_id} ({platform}:{platform_user_id})")
    return {"activated": True}


@router.post("/auth/request-activation")
async def request_activation(
    body: ActivationRequestCreate,
    auth_token: str | None = Cookie(None),
    pool: Pool = Depends(get_db_pool),
) -> dict:
    """Submit a manual activation request for owner review."""
    payload = get_token_payload(auth_token)
    user_id = str(payload["sub"])
    platform = str(payload["platform"])
    platform_user_id = str(payload["platform_user_id"])

    already_activated = await pool.fetchval(
        "SELECT is_activated FROM users WHERE id = $1::uuid", user_id
    )
    if already_activated:
        return {"status": "already_activated"}

    repo = ActivationRequestRepository(pool)
    await repo.create(user_id, platform, platform_user_id, body.note.strip())
    LOGGER.info(f"Activation request submitted: user {user_id} ({platform}:{platform_user_id})")
    return {"status": "pending"}


@router.get("/auth/activation-request")
async def get_activation_request_status(
    auth_token: str | None = Cookie(None),
    pool: Pool = Depends(get_db_pool),
) -> dict:
    """Return the most recent activation request status for the current user."""
    payload = get_token_payload(auth_token)
    user_id = str(payload["sub"])

    repo = ActivationRequestRepository(pool)
    request = await repo.get_for_user(user_id)
    if not request:
        return {"status": None}
    return {
        "status": request["status"],
        "created_at": request["created_at"].isoformat(),
    }


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
