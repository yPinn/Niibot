"""Bot status monitoring API routes"""

import logging

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.config import Settings, get_settings
from core.dependencies import get_current_user_id, require_activated

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/bots",
    tags=["bots"],
    dependencies=[Depends(require_activated)],
)

# Shared client — avoids a new TCP connection on every health check poll
_http_client = httpx.AsyncClient(timeout=10.0)


async def close_bots_http_client() -> None:
    """Close the shared HTTP client. Called on app shutdown."""
    await _http_client.aclose()


class BotStatusResponse(BaseModel):
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
    components: int | None = None
    # Discord
    guilds: int | None = None
    cogs: int | None = None
    ws_latency_ms: int | None = None
    # AI
    ai_model: str | None = None
    ai_status: dict[str, object] | None = None


async def check_bot_health(bot_url: str, bot_name: str) -> BotStatusResponse:
    try:
        response = await _http_client.get(f"{bot_url}/status")

        if response.status_code == 200:
            data = response.json()
            LOGGER.debug(f"{bot_name} bot status check successful: {data}")

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
                components=data.get("components"),
                guilds=data.get("guilds"),
                cogs=data.get("cogs"),
                ws_latency_ms=data.get("ws_latency_ms"),
                ai_model=data.get("ai_model"),
                ai_status=data.get("ai_status"),
            )
        else:
            LOGGER.warning(f"{bot_name} bot health check returned status {response.status_code}")
            return BotStatusResponse(online=False)

    except (httpx.TimeoutException, httpx.ConnectError):
        LOGGER.debug(f"{bot_name} bot offline")
        return BotStatusResponse(online=False)

    except Exception:
        LOGGER.exception(f"Error checking {bot_name} bot status")
        return BotStatusResponse(online=False)


@router.get("/twitch/status", response_model=BotStatusResponse)
async def get_twitch_bot_status(
    _user_id: str = Depends(get_current_user_id),
    settings: Settings = Depends(get_settings),
) -> BotStatusResponse:
    """Get Twitch bot status"""
    return await check_bot_health(settings.twitch_bot_url, "Twitch")


async def _proxy_health(url: str) -> dict:
    try:
        response = await _http_client.get(f"{url}/health")
        if response.status_code == 200:
            return response.json()
        return {"status": "unhealthy", "bot_offline": True}
    except Exception:
        LOGGER.debug("Health proxy unavailable: %s", url)
        return {"status": "unhealthy", "bot_offline": True}


@router.get("/twitch/health")
async def get_twitch_bot_health(
    _user_id: str = Depends(get_current_user_id),
    settings: Settings = Depends(get_settings),
):
    """Twitch bot health check"""
    return await _proxy_health(settings.twitch_bot_url)


@router.get("/discord/status", response_model=BotStatusResponse)
async def get_discord_bot_status(
    _user_id: str = Depends(get_current_user_id),
    settings: Settings = Depends(get_settings),
) -> BotStatusResponse:
    """Get Discord bot status"""
    return await check_bot_health(settings.discord_bot_url, "Discord")


@router.get("/discord/health")
async def get_discord_bot_health(
    _user_id: str = Depends(get_current_user_id),
    settings: Settings = Depends(get_settings),
):
    """Discord bot health check"""
    return await _proxy_health(settings.discord_bot_url)
