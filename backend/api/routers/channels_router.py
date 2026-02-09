"""Channel management API routes"""

import logging

from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.dependencies import (
    get_channel_service,
    get_current_user_id,
    get_db_pool,
    get_twitch_api,
)
from services import TwitchAPIClient

logger = logging.getLogger(__name__)

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


# ============================================
# Endpoints
# ============================================


@router.get("/twitch/monitored", response_model=list[ChannelInfo])
async def get_monitored_channels(
    user_id: str = Depends(get_current_user_id),
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
        logger.debug(f"Found {len(enabled_channels)} enabled channels")

        if not enabled_channels:
            return []

        channel_ids = [ch["channel_id"] for ch in enabled_channels]

        # Fetch user info from Twitch (uses app token internally)
        users_data = await twitch_api.get_users_by_ids(channel_ids)

        if not users_data:
            logger.warning("No user data returned from Twitch API")
            return []

        # Build channel info map
        channels_info = {}
        for user in users_data:
            channels_info[user["login"]] = ChannelInfo(
                id=user["id"],
                name=user["login"],
                display_name=user["display_name"],
                avatar=user["profile_image_url"],
                is_live=False,
                viewer_count=0,
                game_name="",
            )

        # Fetch stream status (uses app token internally)
        user_ids_list = [user["id"] for user in users_data]
        if user_ids_list:
            streams_data = await twitch_api.get_streams(user_ids_list)

            for stream in streams_data:
                stream_user_id = stream["user_id"]
                for channel in channels_info.values():
                    if channel.id == stream_user_id:
                        channel.is_live = True
                        channel.viewer_count = stream["viewer_count"]
                        channel.game_name = stream["game_name"]
                        break

        # Filter out the current user and sort
        result = [ch for ch in channels_info.values() if ch.id != user_id]
        result.sort(key=lambda x: (not x.is_live, x.display_name))

        logger.debug(f"Returning {len(result)} monitored channels for user {user_id}")
        return result

    except Exception as e:
        logger.exception(f"Failed to get monitored channels: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch channels") from None


@router.get("/twitch/my-status", response_model=ChannelStatusResponse)
async def get_my_channel_status(
    user_id: str = Depends(get_current_user_id),
    pool: Pool = Depends(get_db_pool),
) -> ChannelStatusResponse:
    """Get current user's channel status"""
    try:
        channel_service = get_channel_service(pool)
        status = await channel_service.get_channel_status(user_id)
        return ChannelStatusResponse(**status)

    except Exception as e:
        logger.exception(f"Failed to get channel status: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch status") from None


@router.post("/twitch/toggle", response_model=ToggleResponse)
async def toggle_channel(
    request: ChannelToggleRequest,
    user_id: str = Depends(get_current_user_id),
    pool: Pool = Depends(get_db_pool),
) -> ToggleResponse:
    """Enable or disable bot for a channel"""
    try:
        channel_service = get_channel_service(pool)
        success = await channel_service.toggle_channel(request.channel_id, request.enabled)

        if success:
            action = "enabled" if request.enabled else "disabled"
            logger.info(f"Channel {action}: {request.channel_id} by user: {user_id}")
            return ToggleResponse(message=f"Channel {action} successfully")
        else:
            raise HTTPException(status_code=500, detail="Failed to update channel status")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to toggle channel: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


# ============================================
# Channel Defaults (cooldown settings)
# ============================================


@router.get("/defaults", response_model=ChannelDefaultsResponse)
async def get_channel_defaults(
    user_id: str = Depends(get_current_user_id),
    pool: Pool = Depends(get_db_pool),
) -> ChannelDefaultsResponse:
    """Get channel default cooldown settings."""
    from shared.repositories.channel import ChannelRepository

    try:
        repo = ChannelRepository(pool)
        channel = await repo.get_channel(user_id)
        if not channel:
            return ChannelDefaultsResponse(default_cooldown=0)
        return ChannelDefaultsResponse(
            default_cooldown=channel.default_cooldown,
        )
    except Exception as e:
        logger.exception(f"Failed to get channel defaults: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch channel defaults") from None


@router.put("/defaults", response_model=ChannelDefaultsResponse)
async def update_channel_defaults(
    body: ChannelDefaultsUpdate,
    user_id: str = Depends(get_current_user_id),
    pool: Pool = Depends(get_db_pool),
) -> ChannelDefaultsResponse:
    """Update channel default cooldown settings."""
    from shared.repositories.channel import ChannelRepository

    try:
        repo = ChannelRepository(pool)
        channel = await repo.update_channel_defaults(
            user_id,
            default_cooldown=body.default_cooldown,
        )
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        logger.info(f"User {user_id} updated channel defaults")
        return ChannelDefaultsResponse(
            default_cooldown=channel.default_cooldown,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update channel defaults: {e}")
        raise HTTPException(status_code=500, detail="Failed to update channel defaults") from None
