"""Authentication API routes"""

import logging
from typing import Literal
from urllib.parse import quote as _url_quote

from asyncpg import Pool
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from core.config import Settings, get_settings
from core.database import get_database_manager
from core.dependencies import (
    get_admission_service,
    get_auth_service,
    get_channel_service,
    get_current_user_id,
    get_db_pool,
    get_token_payload,
    get_twitch_api,
)
from core.rate_limit import RateLimiter
from services import (
    AdmissionService,
    AuthService,
    IdentityService,
    TenantService,
    TwitchAPIClient,
)
from services.oauth_service import decode_oauth_state, encode_oauth_state
from shared.repositories.activation_code import ActivationCodeRepository

LOGGER: logging.Logger = logging.getLogger(__name__)


# 5 OTP attempts per 10-minute window per user
_otp_rate_limiter = RateLimiter(max_calls=5, period=600.0)

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
    """Handle Twitch OAuth callback.

    Splits cleanly into three concerns:
      1. exchange code for token + fetch user info        (identity proof)
      2. IdentityService.find_or_link                     (identity binding)
      3. AdmissionService.ensure_pending / auto_admit     (admission)
      4. TenantService.ensure_tenant_for_owner            (tenant setup)
      5. CredentialService persistence (still via channel_service.save_token)

    Each layer is idempotent on reauth: an already-active member who reauths
    just walks through (1), (2), and (5) — no admission row is created or
    modified.
    """
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
        # 1. Persist Twitch credentials (broadcaster token + channel row).
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

        # 2. Resolve / create identity (idempotent on reauth, self-healing).
        identity_svc = IdentityService(pool)
        link_result = await identity_svc.find_or_link(
            platform="twitch",
            platform_user_id=platform_user_id,
            username=username,
            display_name=user_info.get("display_name"),
            avatar=user_info.get("avatar"),
        )
        user_id = link_result.user_id

        # 3. Admission. ONLY new users get a pending membership inserted;
        #    existing-but-not-active users keep whatever status they have.
        #    Owner is auto-admitted (replaces the previous SQL bypass).
        admission_svc = AdmissionService(pool)
        is_owner = platform_user_id == str(settings.owner_id)
        if is_owner:
            await admission_svc.auto_admit(user_id, reason="owner")
        elif link_result.is_new_user:
            await admission_svc.ensure_pending(
                user_id,
                reason="first_signup",
                metadata={
                    "platform": "twitch",
                    "platform_user_id": platform_user_id,
                },
            )
        # else: reauth / reconciliation paths — membership is left untouched.

        # 4. Tenant bootstrap (channel + channel_members owner).
        tenant_svc = TenantService(pool)
        await tenant_svc.ensure_tenant_for_owner(
            channel_id=platform_user_id,
            owner_user_id=user_id,
            channel_name=username,
            display_name=user_info.get("display_name"),
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
    admission: AdmissionService = Depends(get_admission_service),
) -> UserInfoResponse:
    """Get current authenticated user information."""
    payload = get_token_payload(auth_token)
    user_id = str(payload["sub"])
    platform_user_id = str(payload["platform_user_id"])

    theme = "system"
    try:
        user_row = await pool.fetchrow("SELECT theme FROM users WHERE id = $1::uuid", user_id)
        if user_row:
            theme = user_row["theme"]

        requires_reauth = await pool.fetchval(
            "SELECT requires_reauth FROM tokens WHERE user_id = $1 AND token_type = 'broadcaster'",
            platform_user_id,
        )
        if requires_reauth:
            raise HTTPException(status_code=401, detail="reauth_required")
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.warning(f"DB error fetching user row for {user_id}: {type(e).__name__}: {e}")

    membership = await admission.get(user_id)
    is_activated = membership is not None and membership.status == "active"

    user_info = await twitch_api.get_user_info(platform_user_id)
    if not user_info:
        raise HTTPException(status_code=404, detail="User not found")

    owner_id_cfg = str(get_settings().owner_id)
    is_owner = platform_user_id == owner_id_cfg
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
    admission: AdmissionService = Depends(get_admission_service),
) -> dict:
    """Activate account using an OTP code from the niibot_auth redemption."""
    payload = get_token_payload(auth_token)
    user_id = str(payload["sub"])
    platform = str(payload["platform"])
    platform_user_id = str(payload["platform_user_id"])

    if await admission.is_active(user_id):
        return {"activated": True}

    if not _otp_rate_limiter.allow(user_id):
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

    # Hash the code only for the audit metadata. The plaintext is never persisted.
    import hashlib

    code_hash = hashlib.sha256(body.code.strip().encode()).hexdigest()
    await admission.grant_via_otp(
        user_id,
        platform=platform,
        platform_user_id=platform_user_id,
        code_hash=code_hash,
    )

    LOGGER.info(f"Account activated: user {user_id} ({platform}:{platform_user_id})")
    return {"activated": True}


@router.post("/auth/request-activation")
async def request_activation(
    auth_token: str | None = Cookie(None),
    admission: AdmissionService = Depends(get_admission_service),
) -> dict:
    """Submit (or re-submit after rejection) an activation request.

    Suspended accounts cannot re-apply through this endpoint — suspension is
    an operator decision and only AdmissionService.reinstate (called from the
    admin router) can lift it.
    """
    payload = get_token_payload(auth_token)
    user_id = str(payload["sub"])

    current = await admission.get(user_id)
    if current is None:
        # Edge case — user pre-dates admission model; create a fresh pending row.
        decision = await admission.ensure_pending(user_id, reason="explicit_request")
        return {"status": decision.membership.status}

    if current.status == "active":
        return {"status": "already_activated"}
    if current.status == "pending":
        return {"status": "pending"}
    if current.status == "suspended":
        # Operator-imposed; user cannot self-lift.
        raise HTTPException(status_code=403, detail="account_suspended")

    # rejected → user explicit re-application
    decision = await admission.reapply(user_id)
    LOGGER.info(f"Activation re-request submitted: user {user_id}")
    return {"status": decision.membership.status}


@router.get("/auth/activation-request")
async def get_activation_request_status(
    auth_token: str | None = Cookie(None),
    admission: AdmissionService = Depends(get_admission_service),
) -> dict:
    """Return the most recent membership status + last decision timestamp."""
    payload = get_token_payload(auth_token)
    user_id = str(payload["sub"])

    membership = await admission.get(user_id)
    if membership is None:
        return {"status": None}

    # Mirror the legacy response shape that the /activate page consumes.
    return {
        "status": membership.status,
        "created_at": membership.updated_at.isoformat(),
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
