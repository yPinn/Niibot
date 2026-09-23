"""Tenant bot-account invitations and isolated public OAuth authorization."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Literal
from urllib.parse import quote, urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from core.config import Settings, get_settings
from core.dependencies import (
    get_bot_account_service,
    get_current_user_id,
    get_twitch_api,
    get_twitch_authorization_service,
    require_owner,
    require_tenant_access,
    require_tenant_owner,
)
from core.rate_limit import RateLimiter
from services.bot_account_service import (
    BotAccountService,
    BotAccountSummary,
    BotInviteCreated,
)
from services.oauth_service import decode_oauth_state, encode_oauth_state
from services.tenant_service import TenantContext
from services.twitch_api import TwitchAPIClient
from services.twitch_authorization_service import (
    AuthorizationRemovalResult,
    AuthorizationStatus,
    CredentialHealth,
    TwitchAuthorizationService,
)
from shared.errors import AppError, NotFoundError
from shared.twitch_scopes import BOT_SCOPES, required_core_scopes

LOGGER = logging.getLogger(__name__)

router = APIRouter(tags=["bot accounts"])
_invite_create_limiter = RateLimiter(max_calls=10, period=60.0)
_public_invite_limiter = RateLimiter(max_calls=60, period=60.0)
_callback_limiter = RateLimiter(max_calls=30, period=60.0)
_authorization_check_limiter = RateLimiter(max_calls=10, period=60.0)
_authorization_remove_limiter = RateLimiter(max_calls=5, period=60.0)
_BOT_CALLBACK_PATH = "/api/auth/twitch/bot/callback"


class BotInviteCreateResponse(BaseModel):
    invite_id: str
    public_url: str
    expires_at: str


class PublicBotInviteResponse(BaseModel):
    channel_name: str
    display_name: str | None
    purpose: str
    status: str
    expires_at: str
    required_scopes: list[str]
    oauth_url: str | None


class DeclineResponse(BaseModel):
    status: str


class SystemBotNotConfiguredError(NotFoundError):
    code = "BOT_ACCOUNT.SYSTEM_NOT_CONFIGURED"
    user_message = "系統 Bot 尚未設定"


class BotAccountResponse(BaseModel):
    platform_user_id: str
    login: str
    display_name: str
    avatar: str | None
    is_system_default: bool
    requires_reauth: bool
    last_validated_at: datetime | None
    revoked_at: datetime | None
    authorization_status: str
    last_checked_at: datetime | None
    linked_at: datetime | None
    is_active: bool
    is_desired: bool


class BotAccountListResponse(BaseModel):
    accounts: list[BotAccountResponse]


class BotInviteStatusResponse(BaseModel):
    invite_id: str
    status: str
    expires_at: datetime
    consumed_at: datetime | None
    account: BotAccountResponse | None


class AuthorizationHealthResponse(BaseModel):
    status: AuthorizationStatus
    last_checked_at: datetime | None
    last_validated_at: datetime | None
    error_code: str | None


class AuthorizationRemovalResponse(BaseModel):
    credential_retained: bool
    upstream_revoke_confirmed: bool


class BroadcasterAuthorizationResponse(AuthorizationHealthResponse):
    channel_id: str
    channel_name: str
    display_name: str | None
    enabled: bool


class CapabilityHealthResponse(BaseModel):
    key: str
    label: str
    credential: Literal["bot", "broadcaster"]
    available: bool
    missing_scopes: list[str]
    core: bool


class TwitchCapabilitySnapshotResponse(BaseModel):
    broadcaster_status: AuthorizationStatus
    bot_status: AuthorizationStatus
    bot_user_id: str
    capabilities: list[CapabilityHealthResponse]


def _request_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _capability_rate_key(public_token: str) -> str:
    return hashlib.sha256(public_token.encode()).hexdigest()[:16]


def _result_redirect(settings: Settings, *, status_value: str, reason: str | None = None) -> str:
    query = {"status": status_value}
    if reason:
        query["reason"] = reason
    return f"{settings.frontend_url}/bot-auth/result?{urlencode(query)}"


def _account_response(
    account: BotAccountSummary,
    *,
    is_system_default: bool,
    system_is_active: bool = False,
    system_is_desired: bool = False,
) -> BotAccountResponse:
    if account.requires_reauth or account.revoked_at is not None:
        authorization_status = "requires_reauthorization"
    elif account.validation_error_code == "provider_unavailable":
        authorization_status = "temporarily_unavailable"
    elif account.last_validated_at is not None:
        authorization_status = "valid"
    else:
        authorization_status = "not_checked"
    return BotAccountResponse(
        platform_user_id=account.platform_user_id,
        login=account.login,
        display_name=account.display_name,
        avatar=account.avatar,
        is_system_default=is_system_default,
        requires_reauth=account.requires_reauth,
        last_validated_at=account.last_validated_at,
        revoked_at=account.revoked_at,
        authorization_status=authorization_status,
        last_checked_at=account.last_checked_at,
        linked_at=account.linked_at,
        is_active=system_is_active if is_system_default else account.is_active,
        is_desired=system_is_desired if is_system_default else account.is_desired,
    )


def _invite_response(created: BotInviteCreated, settings: Settings) -> BotInviteCreateResponse:
    public_url = (
        f"{settings.frontend_url}/bot-invite/{quote(created.public_token, safe='')}?"
        f"{urlencode({'nonce': created.state_nonce})}"
    )
    return BotInviteCreateResponse(
        invite_id=created.id,
        public_url=public_url,
        expires_at=created.expires_at.isoformat(),
    )


@router.get(
    "/api/tenants/{channel_id}/bot-accounts",
    response_model=BotAccountListResponse,
)
async def list_tenant_bot_accounts(
    channel_id: str,
    _tenant: TenantContext = Depends(require_tenant_access),
    service: BotAccountService = Depends(get_bot_account_service),
) -> BotAccountListResponse:
    """Return system Niibot plus only custom accounts mapped to this tenant."""
    system_default = await service.get_system_default()
    custom_accounts = await service.list_for_tenant(channel_id)
    accounts = []
    if system_default is not None:
        accounts.append(
            _account_response(
                system_default,
                is_system_default=True,
                system_is_active=not any(account.is_active for account in custom_accounts),
                system_is_desired=not any(account.is_desired for account in custom_accounts),
            )
        )
    accounts.extend(
        _account_response(account, is_system_default=False) for account in custom_accounts
    )
    return BotAccountListResponse(accounts=accounts)


def _health_response(health: CredentialHealth) -> AuthorizationHealthResponse:
    return AuthorizationHealthResponse(
        status=health.status,
        last_checked_at=health.last_checked_at,
        last_validated_at=health.last_validated_at,
        error_code=health.error_code,
    )


def _removal_response(result: AuthorizationRemovalResult) -> AuthorizationRemovalResponse:
    return AuthorizationRemovalResponse(
        credential_retained=result.credential_retained,
        upstream_revoke_confirmed=result.upstream_revoke_confirmed,
    )


@router.post(
    "/api/tenants/{channel_id}/bot-accounts/{bot_user_id}/authorization-check",
    response_model=AuthorizationHealthResponse,
)
async def check_bot_authorization(
    channel_id: str,
    bot_user_id: str,
    request: Request,
    _action: Literal["twitch-authorization-management"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_tenant_owner),
    bot_accounts: BotAccountService = Depends(get_bot_account_service),
    authorization: TwitchAuthorizationService = Depends(get_twitch_authorization_service),
) -> AuthorizationHealthResponse:
    """Manually recheck a bot credential visible to this tenant."""
    _authorization_check_limiter.require(
        f"bot-check:{tenant.user_id}:{channel_id}:{_request_ip(request)}"
    )
    await bot_accounts.assert_available_to_tenant(channel_id=channel_id, bot_user_id=bot_user_id)
    health = await authorization.check_credential(
        user_id=bot_user_id,
        token_type="bot",
        required_scopes=set(required_core_scopes("bot")),
    )
    return _health_response(health)


@router.delete(
    "/api/tenants/{channel_id}/bot-accounts/{bot_user_id}",
    response_model=AuthorizationRemovalResponse,
)
async def unlink_bot_account(
    channel_id: str,
    bot_user_id: str,
    request: Request,
    _action: Literal["twitch-authorization-management"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_tenant_owner),
    authorization: TwitchAuthorizationService = Depends(get_twitch_authorization_service),
) -> AuthorizationRemovalResponse:
    """Remove only this tenant mapping; revoke the token only after its last mapping."""
    _authorization_remove_limiter.require(
        f"bot-unlink:{tenant.user_id}:{channel_id}:{_request_ip(request)}"
    )
    result = await authorization.unlink_bot_from_tenant(
        channel_id=channel_id,
        bot_user_id=bot_user_id,
        actor_user_id=tenant.user_id,
    )
    return _removal_response(result)


@router.get(
    "/api/tenants/{channel_id}/broadcaster-authorization",
    response_model=BroadcasterAuthorizationResponse,
)
async def get_broadcaster_authorization(
    channel_id: str,
    _tenant: TenantContext = Depends(require_tenant_access),
    authorization: TwitchAuthorizationService = Depends(get_twitch_authorization_service),
) -> BroadcasterAuthorizationResponse:
    summary = await authorization.get_broadcaster_summary(channel_id=channel_id)
    return BroadcasterAuthorizationResponse(**summary.__dict__)


@router.get(
    "/api/tenants/{channel_id}/twitch-capabilities",
    response_model=TwitchCapabilitySnapshotResponse,
)
async def get_twitch_capabilities(
    channel_id: str,
    _tenant: TenantContext = Depends(require_tenant_access),
    authorization: TwitchAuthorizationService = Depends(get_twitch_authorization_service),
    settings: Settings = Depends(get_settings),
) -> TwitchCapabilitySnapshotResponse:
    if not settings.bot_id:
        raise SystemBotNotConfiguredError()
    snapshot = await authorization.get_capability_snapshot(
        channel_id=channel_id,
        system_bot_id=settings.bot_id,
    )
    return TwitchCapabilitySnapshotResponse(
        broadcaster_status=snapshot.broadcaster_status,
        bot_status=snapshot.bot_status,
        bot_user_id=snapshot.bot_user_id,
        capabilities=[CapabilityHealthResponse(**item.__dict__) for item in snapshot.capabilities],
    )


@router.post(
    "/api/tenants/{channel_id}/broadcaster-authorization/check",
    response_model=AuthorizationHealthResponse,
)
async def check_broadcaster_authorization(
    channel_id: str,
    request: Request,
    _action: Literal["twitch-authorization-management"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_tenant_owner),
    authorization: TwitchAuthorizationService = Depends(get_twitch_authorization_service),
) -> AuthorizationHealthResponse:
    _authorization_check_limiter.require(
        f"broadcaster-check:{tenant.user_id}:{channel_id}:{_request_ip(request)}"
    )
    health = await authorization.check_credential(
        user_id=channel_id,
        token_type="broadcaster",
        required_scopes=set(required_core_scopes("broadcaster")),
    )
    return _health_response(health)


@router.delete(
    "/api/tenants/{channel_id}/broadcaster-authorization",
    response_model=AuthorizationRemovalResponse,
)
async def disconnect_broadcaster_authorization(
    channel_id: str,
    request: Request,
    response: Response,
    _action: Literal["twitch-authorization-management"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_tenant_owner),
    authorization: TwitchAuthorizationService = Depends(get_twitch_authorization_service),
) -> AuthorizationRemovalResponse:
    _authorization_remove_limiter.require(
        f"broadcaster-disconnect:{tenant.user_id}:{channel_id}:{_request_ip(request)}"
    )
    result = await authorization.disconnect_broadcaster(
        channel_id=channel_id, owner_user_id=tenant.user_id
    )
    response.delete_cookie(
        key="auth_token",
        path="/",
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return _removal_response(result)


@router.post(
    "/api/tenants/{channel_id}/bot-accounts/invites",
    response_model=BotInviteCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_bot_invite(
    channel_id: str,
    request: Request,
    _action: Literal["bot-account-management"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_tenant_owner),
    service: BotAccountService = Depends(get_bot_account_service),
    settings: Settings = Depends(get_settings),
) -> BotInviteCreateResponse:
    """Create a tenant-owner-only, 30-minute bot credential invitation."""
    _invite_create_limiter.require(f"{tenant.user_id}:{channel_id}:{_request_ip(request)}")
    created = await service.create_invite(
        channel_id=channel_id,
        creator_user_id=tenant.user_id,
    )
    return _invite_response(created, settings)


@router.post(
    "/api/admin/bot-accounts/system-default/reset-invite",
    response_model=BotInviteCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_system_bot_reset_invite(
    request: Request,
    _action: Literal["bot-account-management"] = Header(alias="X-Niibot-Action"),
    owner_channel_id: str = Depends(require_owner),
    creator_user_id: str = Depends(get_current_user_id),
    service: BotAccountService = Depends(get_bot_account_service),
    settings: Settings = Depends(get_settings),
) -> BotInviteCreateResponse:
    """Replace local-script token reset with an expected-account web invite."""
    if not settings.bot_id:
        raise SystemBotNotConfiguredError()
    _invite_create_limiter.require(f"system:{creator_user_id}:{_request_ip(request)}")
    created = await service.create_invite(
        channel_id=owner_channel_id,
        creator_user_id=creator_user_id,
        purpose="system_default_reset",
        expected_bot_user_id=settings.bot_id,
    )
    return _invite_response(created, settings)


@router.post(
    "/api/tenants/{channel_id}/bot-accounts/{bot_user_id}/reauthorize-invite",
    response_model=BotInviteCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_bot_reauthorization_invite(
    channel_id: str,
    bot_user_id: str,
    request: Request,
    _action: Literal["bot-account-management"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_tenant_owner),
    service: BotAccountService = Depends(get_bot_account_service),
    settings: Settings = Depends(get_settings),
) -> BotInviteCreateResponse:
    """Reset a custom credential only after proving it belongs to this tenant."""
    _invite_create_limiter.require(
        f"reauthorize:{tenant.user_id}:{channel_id}:{_request_ip(request)}"
    )
    created = await service.create_invite(
        channel_id=channel_id,
        creator_user_id=tenant.user_id,
        purpose="reauthorize",
        expected_bot_user_id=bot_user_id,
    )
    return _invite_response(created, settings)


@router.get(
    "/api/tenants/{channel_id}/bot-accounts/invites/{invite_id}",
    response_model=BotInviteStatusResponse,
)
async def get_bot_invite_status(
    channel_id: str,
    invite_id: UUID,
    _tenant: TenantContext = Depends(require_tenant_owner),
    service: BotAccountService = Depends(get_bot_account_service),
) -> BotInviteStatusResponse:
    invite = await service.get_invite_status(
        channel_id=channel_id,
        invite_id=str(invite_id),
    )
    account = (
        _account_response(invite.account, is_system_default=False)
        if invite.account is not None
        else None
    )
    return BotInviteStatusResponse(
        invite_id=invite.id,
        status=invite.status,
        expires_at=invite.expires_at,
        consumed_at=invite.consumed_at,
        account=account,
    )


@router.get(
    "/api/public/bot-invites/{public_token}",
    response_model=PublicBotInviteResponse,
)
async def get_public_bot_invite(
    public_token: str,
    request: Request,
    nonce: str = Query(min_length=16, max_length=128),
    service: BotAccountService = Depends(get_bot_account_service),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    settings: Settings = Depends(get_settings),
) -> PublicBotInviteResponse:
    """Return the minimal consent-page contract for the invite holder."""
    _public_invite_limiter.require(f"{_request_ip(request)}:{_capability_rate_key(public_token)}")
    invite = await service.get_public_invite(
        public_token=public_token,
        state_nonce=nonce,
    )
    oauth_url = None
    if invite.status == "pending":
        state_value = encode_oauth_state(
            "bot_authorization",
            f"{invite.invite_id}.{nonce}",
            secret=settings.jwt_secret_key,
        )
        oauth_url = twitch_api.generate_oauth_url(
            state=state_value,
            scopes=BOT_SCOPES,
            redirect_path=_BOT_CALLBACK_PATH,
        )
    return PublicBotInviteResponse(
        channel_name=invite.channel_name,
        display_name=invite.display_name,
        purpose=invite.purpose,
        status=invite.status,
        expires_at=invite.expires_at.isoformat(),
        required_scopes=list(BOT_SCOPES),
        oauth_url=oauth_url,
    )


@router.post(
    "/api/public/bot-invites/{public_token}/decline",
    response_model=DeclineResponse,
)
async def decline_public_bot_invite(
    public_token: str,
    request: Request,
    nonce: str = Query(min_length=16, max_length=128),
    service: BotAccountService = Depends(get_bot_account_service),
) -> DeclineResponse:
    _public_invite_limiter.require(
        f"decline:{_request_ip(request)}:{_capability_rate_key(public_token)}"
    )
    await service.decline_invite(public_token=public_token, state_nonce=nonce)
    return DeclineResponse(status="declined")


@router.get(_BOT_CALLBACK_PATH)
async def bot_oauth_callback(
    request: Request,
    code: str | None = None,
    error: str | None = None,
    state: str | None = None,
    service: BotAccountService = Depends(get_bot_account_service),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Persist a bot credential without creating a User, tenant, or session."""
    _callback_limiter.require(_request_ip(request))
    error_url = _result_redirect(settings, status_value="error", reason="authorization_failed")
    if error or not code:
        return RedirectResponse(error_url)

    decoded_state = decode_oauth_state(state, secret=settings.jwt_secret_key)
    capability = decoded_state.get("uid")
    if decoded_state.get("mode") != "bot_authorization" or not isinstance(capability, str):
        return RedirectResponse(
            _result_redirect(settings, status_value="error", reason="invalid_state")
        )
    try:
        invite_id, state_nonce = capability.split(".", 1)
    except ValueError:
        return RedirectResponse(
            _result_redirect(settings, status_value="error", reason="invalid_state")
        )
    if not invite_id or not state_nonce:
        return RedirectResponse(
            _result_redirect(settings, status_value="error", reason="invalid_state")
        )

    success, _error_message, token_data = await twitch_api.exchange_code_for_token(
        code,
        redirect_path=_BOT_CALLBACK_PATH,
    )
    if not success or not token_data:
        return RedirectResponse(
            _result_redirect(settings, status_value="error", reason="token_exchange_failed")
        )

    platform_user_id = token_data["user_id"]
    user_info = await twitch_api.get_user_info(platform_user_id)
    if not user_info:
        return RedirectResponse(
            _result_redirect(settings, status_value="error", reason="identity_unavailable")
        )

    raw_scopes = token_data.get("scopes")
    granted_scopes = (
        {str(scope) for scope in raw_scopes}
        if isinstance(raw_scopes, list)
        else set(str(raw_scopes or "").split())
    )
    try:
        await service.authorize_invite(
            invite_id=invite_id,
            state_nonce=state_nonce,
            platform_user_id=platform_user_id,
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token", ""),
            scopes=granted_scopes,
            login=user_info.get("name") or platform_user_id,
            display_name=user_info.get("display_name") or user_info.get("name") or platform_user_id,
            avatar=user_info.get("avatar"),
        )
    except AppError as exc:
        reason = exc.code.lower().replace(".", "_")
        return RedirectResponse(_result_redirect(settings, status_value="error", reason=reason))
    except Exception:
        LOGGER.exception("Bot OAuth callback failed after token exchange")
        return RedirectResponse(error_url)

    return RedirectResponse(_result_redirect(settings, status_value="success"))
