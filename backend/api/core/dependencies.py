"""Dependency injection utilities for FastAPI"""

import logging

import asyncpg
from fastapi import Cookie, Depends, HTTPException, Path

from core.config import get_settings
from core.database import get_database_manager
from services import (
    AnalyticsService,
    AuthService,
    ChannelService,
    CommandConfigService,
    EventConfigService,
    TwitchAPIClient,
)
from services.admission_service import AdmissionService
from services.bot_account_service import BotAccountService
from services.game_queue_service import GameQueueService
from services.identity_service import IdentityService
from services.message_trigger_service import MessageTriggerService
from services.notify_stream import NotifyWakeHub
from services.tenant_service import (
    TenantContext,
    TenantService,
)
from services.timer_service import TimerService
from shared.log_context import bind_log_context
from shared.repositories.attendance import AttendanceRepository
from shared.repositories.community_overlay import CommunityOverlayRepository
from shared.repositories.vip import VipRepository
from shared.services.attendance import AttendanceService
from shared.services.community_overlay import CommunityOverlayService
from shared.services.vip import VipService

LOGGER: logging.Logger = logging.getLogger(__name__)

# Notify channel names live next to their feature, not in the generic hub —
# see services/notify_stream.py's module docstring for why this stays one hub.
COMMUNITY_OVERLAY_NOTIFY_CHANNEL = "community_overlay_updates"
VIDEO_QUEUE_NOTIFY_CHANNEL = "video_queue_updates"

_notify_hub: NotifyWakeHub | None = None


def get_auth_service() -> AuthService:
    settings = get_settings()
    return AuthService(
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expire_days=settings.jwt_expire_days,
    )


_twitch_api: TwitchAPIClient | None = None


def get_twitch_api() -> TwitchAPIClient:
    """Singleton: reuses TCP connection and token cache across requests."""
    global _twitch_api
    if _twitch_api is None:
        settings = get_settings()
        _twitch_api = TwitchAPIClient(
            client_id=settings.client_id,
            client_secret=settings.client_secret,
            api_url=settings.api_url,
        )
    return _twitch_api


async def close_twitch_api() -> None:
    """Close the shared TwitchAPIClient. Call on app shutdown."""
    global _twitch_api
    if _twitch_api is not None:
        await _twitch_api.close()
        _twitch_api = None


def get_db_pool() -> asyncpg.Pool:
    db_manager = get_database_manager()
    try:
        return db_manager.pool
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Database not ready") from None


def get_channel_service(pool: asyncpg.Pool = Depends(get_db_pool)) -> ChannelService:
    return ChannelService(pool)


def get_analytics_service(pool: asyncpg.Pool = Depends(get_db_pool)) -> AnalyticsService:
    return AnalyticsService(pool)


def get_command_config_service(pool: asyncpg.Pool = Depends(get_db_pool)) -> CommandConfigService:
    return CommandConfigService(pool)


def get_event_config_service(pool: asyncpg.Pool = Depends(get_db_pool)) -> EventConfigService:
    return EventConfigService(pool)


def get_timer_service(pool: asyncpg.Pool = Depends(get_db_pool)) -> TimerService:
    return TimerService(pool)


def get_trigger_service(pool: asyncpg.Pool = Depends(get_db_pool)) -> MessageTriggerService:
    return MessageTriggerService(pool)


def get_game_queue_service(pool: asyncpg.Pool = Depends(get_db_pool)) -> GameQueueService:
    return GameQueueService(pool)


def get_attendance_service(pool: asyncpg.Pool = Depends(get_db_pool)) -> AttendanceService:
    return AttendanceService(AttendanceRepository(pool))


def get_community_overlay_service(
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> CommunityOverlayService:
    return CommunityOverlayService(CommunityOverlayRepository(pool))


def get_notify_hub() -> NotifyWakeHub:
    """Process-wide singleton: one LISTEN connection for every NOTIFY-woken stream feature."""
    global _notify_hub
    if _notify_hub is None:
        _notify_hub = NotifyWakeHub(
            get_settings().database_url,
            notify_channels=[COMMUNITY_OVERLAY_NOTIFY_CHANNEL, VIDEO_QUEUE_NOTIFY_CHANNEL],
        )
    return _notify_hub


def get_vip_service(pool: asyncpg.Pool = Depends(get_db_pool)) -> VipService:
    return VipService(VipRepository(pool))


def get_token_payload(auth_token: str | None = Cookie(None)) -> dict:
    """Verify JWT and return full payload"""
    auth_service = get_auth_service()

    if not auth_token:
        LOGGER.warning("No auth token provided")
        raise HTTPException(status_code=401, detail="Not logged in")

    payload = auth_service.verify_token(auth_token)

    if not payload:
        LOGGER.warning("Invalid or expired token")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    bind_log_context(user_id=str(payload.get("sub")) if payload.get("sub") else None)
    return payload


def get_identity_service(pool: asyncpg.Pool = Depends(get_db_pool)) -> IdentityService:
    return IdentityService(pool)


def get_admission_service(pool: asyncpg.Pool = Depends(get_db_pool)) -> AdmissionService:
    return AdmissionService(pool)


def get_tenant_service(pool: asyncpg.Pool = Depends(get_db_pool)) -> TenantService:
    return TenantService(pool)


def get_bot_account_service(
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> BotAccountService:
    settings = get_settings()
    return BotAccountService(
        pool,
        token_encryption_key=settings.twitch_token_encryption_key,
    )


async def require_activated(
    payload: dict = Depends(get_token_payload),
    admission: AdmissionService = Depends(get_admission_service),
) -> None:
    """Gate access to feature endpoints: caller's membership must be active.

    Consults memberships.status (the new model). Legacy users.is_activated is
    no longer read; the backfill in migration 080 guarantees a 1:1 mapping.
    """
    user_id = str(payload["sub"])
    if not await admission.is_active(user_id):
        raise HTTPException(status_code=403, detail="Account not activated")


async def get_current_user_id(
    payload: dict = Depends(get_token_payload),
) -> str:
    """Return users.id (UUID) for user-level operations (preferences, etc.)"""
    return str(payload["sub"])


async def get_current_channel_id(
    payload: dict = Depends(get_token_payload),
    _: None = Depends(require_activated),
) -> str:
    """Return platform_user_id — maps to TwitchIO broadcaster.id / Helix broadcaster_id.

    Legacy shim: still returns the caller's own platform_user_id. New code
    should depend on ``require_tenant_access`` instead, which verifies the
    caller actually has a role on the requested channel.
    """
    channel_id = str(payload["platform_user_id"])
    bind_log_context(channel_id=channel_id)
    return channel_id


async def require_owner(channel_id: str = Depends(get_current_channel_id)) -> str:
    """Gate access to owner-only endpoints (the admin router)."""
    if channel_id != str(get_settings().owner_id):
        raise HTTPException(status_code=403, detail="Owner access required")
    return channel_id


async def require_tenant_access(
    channel_id: str = Path(..., description="Tenant channel_id"),
    payload: dict = Depends(get_token_payload),
    tenant: TenantService = Depends(get_tenant_service),
) -> TenantContext:
    """FastAPI dependency: verify caller has at least 'manager' role on the channel.

    Use as ``ctx: TenantContext = Depends(require_tenant_access)`` in any
    router that accepts ``{channel_id}`` in its path. This intentionally does
    not depend on broadcaster admission: a collaborator may have no membership
    for their own channel. TenantService still rejects globally locked accounts
    and workspaces whose owner is not active. For endpoints scoped
    to the caller's own channel without a path parameter, prefer
    ``require_self_tenant_access`` below.
    """
    user_id = str(payload["sub"])
    # TenantService raises AppError subclasses (TENANT.*); the global handler
    # in app.py turns them into the standard envelope with the right status.
    ctx = await tenant.assert_access(
        channel_id=channel_id, user_id=user_id, required_role="manager"
    )
    # channel (the login name) comes free off the context — without it every
    # API log line identifies the tenant only by a numeric id.
    bind_log_context(channel_id=ctx.channel_id, channel=ctx.channel_name, role=ctx.role)
    return ctx


async def require_tenant_owner(
    channel_id: str = Path(..., description="Tenant channel_id"),
    payload: dict = Depends(get_token_payload),
    tenant: TenantService = Depends(get_tenant_service),
) -> TenantContext:
    """Verify the caller owns the requested tenant."""
    user_id = str(payload["sub"])
    ctx = await tenant.assert_access(
        channel_id=channel_id,
        user_id=user_id,
        required_role="owner",
    )
    bind_log_context(channel_id=ctx.channel_id, channel=ctx.channel_name, role=ctx.role)
    return ctx


async def require_self_tenant_access(
    payload: dict = Depends(get_token_payload),
    tenant: TenantService = Depends(get_tenant_service),
    _: None = Depends(require_activated),
) -> TenantContext:
    """Tenant context for the caller's *own* channel.

    Convenience for legacy routes that don't accept channel_id in the URL.
    The channel_id is taken from the JWT's platform_user_id, matching the
    behaviour of get_current_channel_id but now wrapped with proper member
    enforcement so suspended / orphaned tenants are properly rejected.
    """
    user_id = str(payload["sub"])
    channel_id = str(payload["platform_user_id"])
    ctx = await tenant.assert_access(
        channel_id=channel_id, user_id=user_id, required_role="manager"
    )
    bind_log_context(channel_id=ctx.channel_id, channel=ctx.channel_name, role=ctx.role)
    return ctx
