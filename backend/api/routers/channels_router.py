"""Channel management API routes"""

import asyncio
import logging

from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.config import get_settings
from core.dependencies import (
    get_channel_service,
    get_current_channel_id,
    get_db_pool,
    get_twitch_api,
)
from services import TwitchAPIClient

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channels", tags=["channels"])


# ============================================
# Request/Response Models
# ============================================


class ChannelToggleRequest(BaseModel):
    channel_id: str
    enabled: bool


class ChannelInfo(BaseModel):
    id: str
    name: str
    display_name: str
    avatar: str
    is_live: bool
    viewer_count: int = 0
    game_name: str = ""
    title: str = ""


class ChannelStatusResponse(BaseModel):
    subscribed: bool
    channel_id: str
    channel_name: str


class ToggleResponse(BaseModel):
    message: str


class ChannelDefaultsResponse(BaseModel):
    default_cooldown: int


class ChannelDefaultsUpdate(BaseModel):
    default_cooldown: int | None = None


class ModStatusResponse(BaseModel):
    is_moderator: bool


class GrantModResponse(BaseModel):
    granted: bool
    already_mod: bool = False


# ============================================
# Endpoints
# ============================================


@router.get("/twitch/monitored", response_model=list[ChannelInfo])
async def get_monitored_channels(
    channel_id: str = Depends(get_current_channel_id),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    pool: Pool = Depends(get_db_pool),
) -> list[ChannelInfo]:
    """Get list of monitored channels with their live status.

    Uses app access token for Twitch API calls (public endpoints).
    User token is not required for fetching user info and stream status.
    """
    try:
        channel_service = get_channel_service(pool)

        # Get enabled channels from database
        enabled_channels = await channel_service.get_enabled_channels()
        LOGGER.debug(f"Found {len(enabled_channels)} enabled channels")

        if not enabled_channels:
            return []

        channel_ids = [ch["channel_id"] for ch in enabled_channels]

        # Fetch user info and stream status in parallel (both use app token)
        users_data, streams_data = await asyncio.gather(
            twitch_api.get_users_by_ids(channel_ids),
            twitch_api.get_streams(channel_ids),
        )

        if not users_data:
            LOGGER.warning("No user data returned from Twitch API")
            return []

        # Index live streams by user_id for O(1) lookup
        live_map: dict[str, dict] = {s["user_id"]: s for s in streams_data}

        # Build channel info list
        channels_info: dict[str, ChannelInfo] = {}
        for user in users_data:
            uid = user["id"]
            stream = live_map.get(uid)
            channels_info[user["login"]] = ChannelInfo(
                id=uid,
                name=user["login"],
                display_name=user["display_name"],
                avatar=user["profile_image_url"],
                is_live=stream is not None,
                viewer_count=stream["viewer_count"] if stream else 0,
                game_name=stream["game_name"] if stream else "",
                title=stream["title"] if stream else "",
            )

        # Filter out the current user's channel and sort
        result = [ch for ch in channels_info.values() if ch.id != channel_id]
        result.sort(key=lambda x: (not x.is_live, x.display_name))

        LOGGER.debug(f"Returning {len(result)} monitored channels for channel {channel_id}")
        return result

    except Exception:
        LOGGER.exception("Failed to get monitored channels")
        raise HTTPException(status_code=500, detail="Failed to fetch channels") from None


@router.get("/twitch/my-status", response_model=ChannelStatusResponse)
async def get_my_channel_status(
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> ChannelStatusResponse:
    """Get current user's channel status"""
    try:
        channel_service = get_channel_service(pool)
        status = await channel_service.get_channel_status(channel_id)
        return ChannelStatusResponse(**status)

    except Exception:
        LOGGER.exception("Failed to get channel status")
        raise HTTPException(status_code=500, detail="Failed to fetch status") from None


@router.post("/twitch/toggle", response_model=ToggleResponse)
async def toggle_channel(
    request: ChannelToggleRequest,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> ToggleResponse:
    """Enable or disable bot for a channel"""
    try:
        if request.channel_id != channel_id:
            raise HTTPException(status_code=403, detail="Cannot toggle another channel")

        channel_service = get_channel_service(pool)
        success = await channel_service.toggle_channel(channel_id, request.enabled)

        if success:
            action = "enabled" if request.enabled else "disabled"
            LOGGER.info(f"Channel {action}: {channel_id}")
            return ToggleResponse(message=f"Channel {action} successfully")
        else:
            raise HTTPException(status_code=500, detail="Failed to update channel status")

    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to toggle channel")
        raise HTTPException(status_code=500, detail="Failed to toggle channel") from None


# ============================================
# Bot Mod Status
# ============================================


@router.get("/twitch/mod-status", response_model=ModStatusResponse)
async def get_bot_mod_status(
    channel_id: str = Depends(get_current_channel_id),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    pool: Pool = Depends(get_db_pool),
) -> ModStatusResponse:
    """Check whether the bot currently holds moderator status in the caller's channel."""
    from fastapi.responses import JSONResponse

    channel_service = get_channel_service(pool)
    token = await channel_service.get_token_with_refresh(channel_id, twitch_api)
    if not token:
        return JSONResponse(  # type: ignore[return-value]
            status_code=403,
            headers={"X-Reauth-Required": "true"},
            content={"detail": "Token unavailable or missing required scope"},
        )
    bot_id = get_settings().bot_id
    is_mod = await twitch_api.check_bot_is_moderator(channel_id, bot_id, token)
    return ModStatusResponse(is_moderator=is_mod)


@router.post("/twitch/grant-mod", response_model=GrantModResponse)
async def grant_bot_mod(
    channel_id: str = Depends(get_current_channel_id),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    pool: Pool = Depends(get_db_pool),
) -> GrantModResponse:
    """Grant the bot moderator status in the caller's channel."""
    from fastapi.responses import JSONResponse

    channel_service = get_channel_service(pool)
    token = await channel_service.get_token_with_refresh(channel_id, twitch_api)
    if not token:
        return JSONResponse(  # type: ignore[return-value]
            status_code=403,
            headers={"X-Reauth-Required": "true"},
            content={"detail": "Token unavailable or missing required scope"},
        )

    bot_id = get_settings().bot_id
    try:
        resp = await twitch_api.add_moderator(channel_id, bot_id, token)
    except Exception:
        LOGGER.exception("Failed to call Twitch grant-mod API")
        raise HTTPException(status_code=500, detail="Failed to grant moderator status") from None

    if resp.status_code == 204:
        LOGGER.info(f"Granted bot mod for channel {channel_id}")
        return GrantModResponse(granted=True)

    if resp.status_code == 422:
        return GrantModResponse(granted=False, already_mod=True)

    if resp.status_code in (401, 403):
        return JSONResponse(  # type: ignore[return-value]
            status_code=403,
            headers={"X-Reauth-Required": "true"},
            content={"detail": "Missing required Twitch scope"},
        )

    LOGGER.error(f"Unexpected grant-mod response {resp.status_code}: {resp.text}")
    raise HTTPException(status_code=502, detail="Twitch API error")


# ============================================
# Channel Defaults (cooldown settings)
# ============================================


@router.get("/defaults", response_model=ChannelDefaultsResponse)
async def get_channel_defaults(
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> ChannelDefaultsResponse:
    """Get channel default cooldown settings."""
    from shared.repositories.channel import ChannelRepository

    try:
        repo = ChannelRepository(pool)
        channel = await repo.get_channel(channel_id)
        if not channel:
            return ChannelDefaultsResponse(default_cooldown=0)
        return ChannelDefaultsResponse(
            default_cooldown=channel.default_cooldown,
        )
    except Exception:
        LOGGER.exception("Failed to get channel defaults")
        raise HTTPException(status_code=500, detail="Failed to fetch channel defaults") from None


@router.put("/defaults", response_model=ChannelDefaultsResponse)
async def update_channel_defaults(
    body: ChannelDefaultsUpdate,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> ChannelDefaultsResponse:
    """Update channel default cooldown settings."""
    from shared.repositories.channel import ChannelRepository

    try:
        repo = ChannelRepository(pool)
        channel = await repo.update_channel_defaults(
            channel_id,
            default_cooldown=body.default_cooldown,
        )
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        LOGGER.info(f"Channel {channel_id} updated channel defaults")
        return ChannelDefaultsResponse(
            default_cooldown=channel.default_cooldown,
        )
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to update channel defaults")
        raise HTTPException(status_code=500, detail="Failed to update channel defaults") from None
