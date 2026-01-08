"""Dependency injection utilities for FastAPI"""

import logging
from typing import Optional

import asyncpg
from fastapi import Cookie, HTTPException
from services import AnalyticsService, AuthService, ChannelService, TwitchAPIClient

from core.config import get_settings
from core.database import get_database_manager

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


def get_twitch_api() -> TwitchAPIClient:
    """Get TwitchAPIClient instance (dependency injection)"""
    settings = get_settings()
    return TwitchAPIClient(
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        api_url=settings.api_url,
    )


async def get_db_pool() -> asyncpg.Pool:
    """Get database pool (dependency injection)"""
    db_manager = get_database_manager()
    return db_manager.pool


def get_channel_service(pool: asyncpg.Pool) -> ChannelService:
    """Get ChannelService instance (dependency injection)"""
    return ChannelService(pool)


def get_analytics_service(pool: asyncpg.Pool) -> AnalyticsService:
    """Get AnalyticsService instance (dependency injection)"""
    return AnalyticsService(pool)


# ============================================
# Authentication Dependencies
# ============================================


async def get_current_user_id(
    auth_token: Optional[str] = Cookie(None),
) -> str:
    """
    Verify authentication and return current user_id

    Raises:
        HTTPException: If not authenticated or token invalid
    """
    auth_service = get_auth_service()

    if not auth_token:
        logger.warning("No auth token provided")
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id = auth_service.verify_token(auth_token)

    if not user_id:
        logger.warning("Invalid or expired token")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return str(user_id)


# ============================================
# Combined Dependencies (for convenience)
# ============================================


async def require_auth_with_channel_service(
    auth_token: Optional[str] = Cookie(None),
) -> tuple[str, ChannelService]:
    """
    Require authentication and return (user_id, channel_service)

    Convenient dependency for endpoints that need both auth and channel operations
    """
    user_id = await get_current_user_id(auth_token)
    pool = await get_db_pool()
    channel_service = get_channel_service(pool)
    return user_id, channel_service


async def require_auth_with_analytics_service(
    auth_token: Optional[str] = Cookie(None),
) -> tuple[str, AnalyticsService]:
    """
    Require authentication and return (user_id, analytics_service)

    Convenient dependency for endpoints that need both auth and analytics operations
    """
    user_id = await get_current_user_id(auth_token)
    pool = await get_db_pool()
    analytics_service = get_analytics_service(pool)
    return user_id, analytics_service
