"""Dependency injection utilities for FastAPI"""

import logging

import asyncpg
from fastapi import Cookie, Depends, HTTPException

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
from services.game_queue_service import GameQueueService
from services.message_trigger_service import MessageTriggerService
from services.timer_service import TimerService

LOGGER: logging.Logger = logging.getLogger(__name__)


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

    return payload


async def get_current_user_id(
    auth_token: str | None = Cookie(None),
) -> str:
    """Return users.id (UUID) for user-level operations (preferences, etc.)"""
    payload = get_token_payload(auth_token)
    return str(payload["sub"])


async def get_current_channel_id(
    auth_token: str | None = Cookie(None),
) -> str:
    """Return platform_user_id — maps to TwitchIO broadcaster.id / Helix broadcaster_id"""
    payload = get_token_payload(auth_token)
    return str(payload["platform_user_id"])
