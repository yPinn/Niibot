"""Bot status monitoring API routes"""

import logging

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bots", tags=["bots"])

settings = get_settings()


class BotStatusResponse(BaseModel):
    """Bot status response"""

    online: bool
    service: str | None = None
    bot_id: str | None = None
    uptime_seconds: int | None = None
    connected_channels: int | None = None


async def check_bot_health(bot_url: str, bot_name: str) -> BotStatusResponse:
    """Check bot health status"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{bot_url}/status",
                timeout=8.0,
            )

            if response.status_code == 200:
                data = response.json()
                logger.debug(f"{bot_name} bot status check successful: {data}")

                return BotStatusResponse(
                    online=True,
                    service=data.get("service"),
                    bot_id=data.get("bot_id"),
                    uptime_seconds=data.get("uptime_seconds"),
                    connected_channels=data.get("connected_channels"),
                )
            else:
                logger.warning(
                    f"{bot_name} bot health check returned status {response.status_code}"
                )
                return BotStatusResponse(online=False)

    except httpx.TimeoutException:
        logger.warning(f"{bot_name} bot health check timeout (bot may be offline)")
        return BotStatusResponse(online=False)

    except httpx.ConnectError:
        logger.warning(f"Cannot connect to {bot_name} bot at {bot_url} (bot offline)")
        return BotStatusResponse(online=False)

    except Exception as e:
        logger.exception(f"Error checking {bot_name} bot status: {e}")
        return BotStatusResponse(online=False)


@router.get("/twitch/status", response_model=BotStatusResponse)
async def get_twitch_bot_status() -> BotStatusResponse:
    """Get Twitch bot status"""
    return await check_bot_health(settings.twitch_bot_url, "Twitch")


@router.get("/twitch/health")
async def get_twitch_bot_health():
    """Twitch bot health check"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.twitch_bot_url}/health",
                timeout=8.0,
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {"status": "unhealthy", "bot_offline": True}

    except Exception:
        return {"status": "unhealthy", "bot_offline": True}


@router.get("/discord/status", response_model=BotStatusResponse)
async def get_discord_bot_status() -> BotStatusResponse:
    """Get Discord bot status"""
    return await check_bot_health(settings.discord_bot_url, "Discord")


@router.get("/discord/health")
async def get_discord_bot_health():
    """Discord bot health check"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.discord_bot_url}/health",
                timeout=8.0,
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {"status": "unhealthy", "bot_offline": True}

    except Exception:
        return {"status": "unhealthy", "bot_offline": True}
