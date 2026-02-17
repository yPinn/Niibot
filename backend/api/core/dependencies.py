"""Dependency injection utilities for FastAPI"""

import logging

import asyncpg
from fastapi import Cookie, HTTPException

from core.config import get_settings
from core.database import get_database_manager
from services import (
    AnalyticsService,
    AuthService,
    ChannelService,
    DiscordAPIClient,
    TwitchAPIClient,
)

logger = logging.getLogger(__name__)


# ============================================
# Service Dependencies
# ============================================


def get_auth_service() -> AuthService:
    """Get AuthService instance (dependency injection)"""
    settings = get_settings()
    return AuthService(
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expire_days=settings.jwt_expire_days,
    )


_twitch_api: TwitchAPIClient | None = None


def get_twitch_api() -> TwitchAPIClient:
    """Get shared TwitchAPIClient singleton (connection reuse + token cache)."""
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


def get_discord_api() -> DiscordAPIClient:
    """Get DiscordAPIClient instance (dependency injection)"""
    settings = get_settings()
    return DiscordAPIClient(
        client_id=settings.discord_client_id,
        client_secret=settings.discord_client_secret,
        api_url=settings.api_url,
    )


def get_db_pool() -> asyncpg.Pool:
    db_manager = get_database_manager()
    if db_manager._pool is None:
        raise HTTPException(status_code=503, detail="Database not ready")
    return db_manager._pool


def get_channel_service(pool: asyncpg.Pool) -> ChannelService:
    """Get ChannelService instance (dependency injection)"""
    return ChannelService(pool)


def get_analytics_service(pool: asyncpg.Pool) -> AnalyticsService:
    """Get AnalyticsService instance (dependency injection)"""
    return AnalyticsService(pool)


# ============================================
# Authentication Dependencies
# ============================================


def _get_token_payload(auth_token: str | None = Cookie(None)) -> dict:
    """Verify JWT and return full payload"""
    auth_service = get_auth_service()

    if not auth_token:
        logger.warning("No auth token provided")
        raise HTTPException(status_code=401, detail="Not logged in")

    payload = auth_service.verify_token(auth_token)

    if not payload:
        logger.warning("Invalid or expired token")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return payload


async def get_current_user_id(
    auth_token: str | None = Cookie(None),
) -> str:
    """Return users.id (UUID) for user-level operations (preferences, etc.)"""
    payload = _get_token_payload(auth_token)
    return str(payload["sub"])


async def get_current_channel_id(
    auth_token: str | None = Cookie(None),
) -> str:
    """Return platform_user_id for channel-level operations

    Maps to TwitchIO broadcaster.id / Helix broadcaster_id
    """
    payload = _get_token_payload(auth_token)
    return str(payload["platform_user_id"])


# ============================================
# Combined Dependencies (for convenience)
# ============================================


async def require_auth_with_channel_service(
    auth_token: str | None = Cookie(None),
) -> tuple[str, ChannelService]:
    """
    Require authentication and return (channel_id, channel_service)

    Convenient dependency for endpoints that need both auth and channel operations
    """
    channel_id = await get_current_channel_id(auth_token)
    pool = get_db_pool()
    channel_service = get_channel_service(pool)
    return channel_id, channel_service


async def require_auth_with_analytics_service(
    auth_token: str | None = Cookie(None),
) -> tuple[str, AnalyticsService]:
    """
    Require authentication and return (channel_id, analytics_service)

    Convenient dependency for endpoints that need both auth and analytics operations
    """
    channel_id = await get_current_channel_id(auth_token)
    pool = get_db_pool()
    analytics_service = get_analytics_service(pool)
    return channel_id, analytics_service
