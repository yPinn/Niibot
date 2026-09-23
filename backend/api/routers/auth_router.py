"""Authentication API routes"""

import hashlib
import logging
from typing import Literal
from urllib.parse import quote as _url_quote

from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from core.config import Settings, get_settings
from core.database import get_database_manager
from core.dependencies import (
    get_active_session_payload,
    get_admission_service,
    get_auth_service,
    get_channel_service,
    get_current_user_id,
    get_db_pool,
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
from services.admission_service import MembershipLockedError
from services.oauth_service import decode_oauth_state, encode_oauth_state
from shared.errors import AccessDeniedError, AppError, NotFoundError, RateLimitedError
from shared.repositories.activation_code import ActivationCodeRepository

LOGGER: logging.Logger = logging.getLogger(__name__)


# 5 OTP attempts per 10-minute window per user
_otp_rate_limiter = RateLimiter(max_calls=5, period=600.0)

router = APIRouter(prefix="/api", tags=["authentication"])


class ReauthRequiredError(AppError):
    code = "AUTH.REAUTH_REQUIRED"
    http_status = 401
    user_message = "Twitch 授權需要重新登入"


class AuthUserNotFoundError(NotFoundError):
    code = "AUTH.USER_NOT_FOUND"
    user_message = "找不到你的帳號資料"


class TooManyAttemptsError(RateLimitedError):
    code = "AUTH.TOO_MANY_ATTEMPTS"
    user_message = "嘗試次數太多，請稍後再試"


class AccountSuspendedError(AccessDeniedError):
    code = "AUTH.ACCOUNT_SUSPENDED"
    user_message = "你的帳號已被停權"


class AccountRejectedError(AccessDeniedError):
    code = "AUTH.ACCOUNT_REJECTED"
    user_message = "你的授權申請未通過，請聯繫管理員"


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


@router.get("/auth/twitch/collaborator/oauth", response_model=OAuthURLResponse)
async def get_twitch_collaborator_oauth_url(
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    settings: Settings = Depends(get_settings),
) -> OAuthURLResponse:
    """Start identity-only OAuth for a user managing someone else's tenant."""
    redirect_path = "/api/auth/twitch/collaborator/callback"
    state = encode_oauth_state("collaborator_login", secret=settings.jwt_secret_key)
    oauth_url = twitch_api.generate_oauth_url(
        state=state,
        scopes=[],
        redirect_path=redirect_path,
    )
    return OAuthURLResponse(
        oauth_url=oauth_url,
        redirect_uri=f"{settings.api_url}{redirect_path}",
    )


@router.get("/auth/twitch/collaborator/callback")
async def twitch_collaborator_oauth_callback(
    code: str | None = None,
    error: str | None = None,
    state: str | None = None,
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Create a session for an existing tenant collaborator grant.

    This flow proves identity only. It never persists the returned OAuth token,
    creates a channel, runs broadcaster admission, or grants tenant access.
    """
    error_redirect = f"{settings.frontend_url}/login"
    if error:
        return RedirectResponse(url=f"{error_redirect}?error={_url_quote(error, safe='')}")

    decoded_state = decode_oauth_state(state, secret=settings.jwt_secret_key)
    if decoded_state.get("mode") != "collaborator_login":
        return RedirectResponse(url=f"{error_redirect}?error=invalid_state")
    if not code:
        return RedirectResponse(url=f"{error_redirect}?error=no_code")

    try:
        pool = get_database_manager().pool
    except RuntimeError:
        return RedirectResponse(url=f"{error_redirect}?error=db_not_ready")

    redirect_path = "/api/auth/twitch/collaborator/callback"
    success, error_msg, token_data = await twitch_api.exchange_code_for_token(
        code, redirect_path=redirect_path
    )
    if not success or not token_data:
        safe_error = _url_quote(error_msg or "token_exchange_failed", safe="")
        return RedirectResponse(url=f"{error_redirect}?error={safe_error}")

    platform_user_id = token_data["user_id"]
    user_info = await twitch_api.get_user_info(platform_user_id)
    if not user_info:
        return RedirectResponse(url=f"{error_redirect}?error=user_fetch_failed")
    username = user_info.get("name") or user_info.get("display_name") or platform_user_id

    try:
        identity_result = await IdentityService(pool).find_or_link(
            platform="twitch",
            platform_user_id=platform_user_id,
            username=username,
            display_name=user_info.get("display_name"),
            avatar=user_info.get("avatar"),
        )
        user_id = identity_result.user_id

        membership = await AdmissionService(pool).get(user_id)
        if membership is not None and membership.status in {"suspended", "rejected"}:
            return RedirectResponse(url=f"{error_redirect}?error=account_locked")

        tenants = await TenantService(pool).list_user_tenants(user_id)
        if not tenants:
            return RedirectResponse(url=f"{error_redirect}?error=no_tenant_access")
        session_version = await pool.fetchval(
            "SELECT session_version FROM users WHERE id = $1::uuid", user_id
        )
    except Exception as exc:
        LOGGER.error(
            "DB error during collaborator OAuth for %s: %s",
            platform_user_id,
            type(exc).__name__,
        )
        return RedirectResponse(url=f"{error_redirect}?error=db_timeout")

    jwt_token = auth_service.create_access_token(
        user_id=user_id,
        platform="twitch",
        platform_user_id=platform_user_id,
        session_version=int(session_version or 1),
    )
    response = RedirectResponse(url=f"{settings.frontend_url}/dashboard/{tenants[0].channel_id}")
    response.set_cookie(
        key="auth_token",
        value=jwt_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.jwt_expire_days * 24 * 60 * 60,
    )
    LOGGER.info("Collaborator logged in: twitch:%s", platform_user_id)
    return response


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

    Splits cleanly into distinct concerns:
      1. exchange code for token + fetch user info        (identity proof)
      2. IdentityService.find_or_link                     (identity binding)
      3. AdmissionService.activate_if_entitled / auto_admit  (admission)
      4. TenantService.ensure_tenant_for_owner            (tenant setup)
      5. CredentialService persistence (still via channel_service.save_token)

    Each layer is idempotent on reauth: an already-active member who reauths
    just walks through (1), (2), and (5). Admission never creates a pending
    row here — a non-owner is activated only if they hold a live channel-points
    grant (consumed in step 3); otherwise they land on /activate.
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

        # 3. Admission. The owner is auto-admitted. Everyone else is activated
        #    iff they hold a live channel-points grant (consumed here in one
        #    transaction); no pending row is created for users who have not
        #    redeemed, and suspended/rejected members are left locked.
        admission_svc = AdmissionService(pool)
        if platform_user_id == str(settings.owner_id):
            await admission_svc.auto_admit(user_id, reason="owner")
        else:
            await admission_svc.activate_if_entitled(
                user_id,
                platform="twitch",
                platform_user_id=platform_user_id,
            )

        # 4. Tenant bootstrap (channel + channel_members owner).
        tenant_svc = TenantService(pool)
        await tenant_svc.ensure_tenant_for_owner(
            channel_id=platform_user_id,
            owner_user_id=user_id,
            channel_name=username,
            display_name=user_info.get("display_name"),
        )
        session_version = await pool.fetchval(
            "SELECT session_version FROM users WHERE id = $1::uuid", user_id
        )
    except Exception as e:
        LOGGER.error(f"DB error during Twitch OAuth for {username}: {type(e).__name__}: {e}")
        return RedirectResponse(url=f"{error_redirect}?error=db_timeout")

    jwt_token = auth_service.create_access_token(
        user_id=user_id,
        platform="twitch",
        platform_user_id=platform_user_id,
        session_version=int(session_version or 1),
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
    payload: dict = Depends(get_active_session_payload),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    pool: Pool = Depends(get_db_pool),
    admission: AdmissionService = Depends(get_admission_service),
) -> UserInfoResponse:
    """Get current authenticated user information."""
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
            raise ReauthRequiredError()
    except AppError:
        raise
    except Exception as e:
        LOGGER.warning(f"DB error fetching user row for {user_id}: {type(e).__name__}: {e}")

    membership = await admission.get(user_id)
    is_activated = membership is not None and membership.status == "active"

    user_info = await twitch_api.get_user_info(platform_user_id)
    if not user_info:
        raise AuthUserNotFoundError(context={"platform_user_id": platform_user_id})

    owner_id_cfg = str(get_settings().owner_id)
    is_owner = platform_user_id == owner_id_cfg
    return UserInfoResponse(
        **user_info, platform="twitch", theme=theme, is_activated=is_activated, is_owner=is_owner
    )


@router.post("/auth/logout", response_model=LogoutResponse)
async def logout(
    response: Response,
    payload: dict = Depends(get_active_session_payload),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> LogoutResponse:
    """Logout current user by clearing auth cookie"""
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
    payload: dict = Depends(get_active_session_payload),
    pool: Pool = Depends(get_db_pool),
) -> dict:
    """Return the pending activation code for the current user, if one exists."""
    platform = str(payload["platform"])
    platform_user_id = str(payload["platform_user_id"])

    repo = ActivationCodeRepository(pool)
    code = await repo.get_plain_code(platform, platform_user_id)
    return {"code": code}


@router.post("/auth/activate")
async def activate_account(
    body: ActivateRequest,
    payload: dict = Depends(get_active_session_payload),
    pool: Pool = Depends(get_db_pool),
    admission: AdmissionService = Depends(get_admission_service),
) -> dict:
    """Activate an account by typing an owner_manual code on /activate.

    Channel-points redeemers never reach here — their grant is consumed
    automatically on login. This path is for codes the owner handed out.
    Code consumption and the membership transition run in one transaction,
    so a failure at either step leaves the code unused.
    """
    user_id = str(payload["sub"])
    platform = str(payload["platform"])
    platform_user_id = str(payload["platform_user_id"])

    membership = await admission.get(user_id)
    if membership and membership.status == "active":
        return {"activated": True}
    if membership and membership.status == "suspended":
        raise AccountSuspendedError()
    if membership and membership.status == "rejected":
        raise AccountRejectedError()

    if not _otp_rate_limiter.allow(user_id):
        raise TooManyAttemptsError()

    code = body.code.strip()
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    repo = ActivationCodeRepository(pool)
    try:
        async with pool.acquire() as conn, conn.transaction():
            redeemed = await repo.redeem(code, platform, platform_user_id, user_id, conn=conn)
            if not redeemed:
                # Machine-readable detail: the /activate page branches on this
                # exact string to show the "code invalid/expired" hint.
                raise HTTPException(status_code=400, detail="invalid_or_expired_code")
            await admission.grant_via_otp(
                user_id,
                platform=platform,
                platform_user_id=platform_user_id,
                code_hash=code_hash,
                conn=conn,
            )
    except MembershipLockedError:
        raise AccountSuspendedError() from None

    LOGGER.info(f"Account activated: user {user_id} ({platform}:{platform_user_id})")
    return {"activated": True}


@router.get("/auth/activation-request")
async def get_activation_request_status(
    payload: dict = Depends(get_active_session_payload),
    admission: AdmissionService = Depends(get_admission_service),
) -> dict:
    """Return the most recent membership status + last decision timestamp."""
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
