"""Bot status monitoring API routes"""

import logging

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.config import get_settings
from core.dependencies import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bots", tags=["bots"])

settings = get_settings()

# Shared client — avoids a new TCP connection on every health check poll
_http_client = httpx.AsyncClient(timeout=10.0)


async def close_bots_http_client() -> None:
    """Close the shared HTTP client. Called on app shutdown."""
    await _http_client.aclose()


class BotStatusResponse(BaseModel):
    """Bot status response"""

    online: bool
    service: str | None = None
    version: str | None = None
    git_commit: str | None = None
    started_at: str | None = None
    bot_id: str | None = None
    uptime_seconds: int | None = None
    ready: bool | None = None
    # Twitch
    connected_channels: int | None = None
    # Discord
    guilds: int | None = None
    ws_latency_ms: int | None = None


async def check_bot_health(bot_url: str, bot_name: str) -> BotStatusResponse:
    """Check bot health status"""
    try:
        response = await _http_client.get(f"{bot_url}/status")

        if response.status_code == 200:
            data = response.json()
            logger.debug(f"{bot_name} bot status check successful: {data}")

            return BotStatusResponse(
                online=True,
                service=data.get("service"),
                version=data.get("version"),
                git_commit=data.get("git_commit"),
                started_at=data.get("started_at"),
                bot_id=data.get("bot_id"),
                uptime_seconds=data.get("uptime_seconds"),
                ready=data.get("ready"),
                connected_channels=data.get("connected_channels"),
                guilds=data.get("guilds"),
                ws_latency_ms=data.get("ws_latency_ms"),
            )
        else:
            logger.warning(f"{bot_name} bot health check returned status {response.status_code}")
            return BotStatusResponse(online=False)

    except (httpx.TimeoutException, httpx.ConnectError):
        logger.debug(f"{bot_name} bot offline")
        return BotStatusResponse(online=False)

    except Exception:
        logger.exception("Error checking {bot_name} bot status")
        return BotStatusResponse(online=False)


@router.get("/twitch/status", response_model=BotStatusResponse)
async def get_twitch_bot_status(
    _user_id: str = Depends(get_current_user_id),
) -> BotStatusResponse:
    """Get Twitch bot status"""
    return await check_bot_health(settings.twitch_bot_url, "Twitch")


@router.get("/twitch/health")
async def get_twitch_bot_health(
    _user_id: str = Depends(get_current_user_id),
):
    """Twitch bot health check"""
    try:
        response = await _http_client.get(f"{settings.twitch_bot_url}/health")
        if response.status_code == 200:
            return response.json()
        return {"status": "unhealthy", "bot_offline": True}
    except Exception:
        return {"status": "unhealthy", "bot_offline": True}


@router.get("/discord/status", response_model=BotStatusResponse)
async def get_discord_bot_status(
    _user_id: str = Depends(get_current_user_id),
) -> BotStatusResponse:
    """Get Discord bot status"""
    return await check_bot_health(settings.discord_bot_url, "Discord")


@router.get("/discord/health")
async def get_discord_bot_health(
    _user_id: str = Depends(get_current_user_id),
):
    """Discord bot health check"""
    try:
        response = await _http_client.get(f"{settings.discord_bot_url}/health")
        if response.status_code == 200:
            return response.json()
        return {"status": "unhealthy", "bot_offline": True}
    except Exception:
        return {"status": "unhealthy", "bot_offline": True}
