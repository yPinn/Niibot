"""Channel monitoring API routes"""

import logging

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel
from services import auth as auth_service
from services import channel as channel_service
from services import twitch as twitch_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channels", tags=["channels"])


class ChannelToggleRequest(BaseModel):
    channel_id: str
    enabled: bool


@router.get("/monitored")
async def get_monitored_channels(auth_token: str | None = Cookie(None)):
    if not auth_token:
        logger.warning("No auth token provided")
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id = auth_service.verify_token(auth_token)

    if not user_id:
        logger.warning("Invalid or expired token")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    try:
        channels = await twitch_service.get_monitored_channels(user_id)
        return channels
    except Exception as e:
        logger.error(f"Failed to get monitored channels: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch channels")


@router.get("/my-status")
async def get_my_channel_status(auth_token: str | None = Cookie(None)):
    if not auth_token:
        logger.warning("No auth token provided")
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id = auth_service.verify_token(auth_token)

    if not user_id:
        logger.warning("Invalid or expired token")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    try:
        status = await channel_service.get_my_channel_status(user_id)
        return status
    except Exception as e:
        logger.error(f"Failed to get my channel status: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch status")


@router.post("/toggle")
async def toggle_channel(request: ChannelToggleRequest, auth_token: str | None = Cookie(None)):
    if not auth_token:
        logger.warning("No auth token provided")
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id = auth_service.verify_token(auth_token)

    if not user_id:
        logger.warning("Invalid or expired token")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    try:
        success = await channel_service.toggle_channel(request.channel_id, request.enabled)

        if success:
            action = "enabled" if request.enabled else "disabled"
            logger.info(f"Channel {request.channel_id} {action} by user {user_id}")
            return {"message": f"Channel {action} successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to update channel status")

    except Exception as e:
        logger.exception(f"Failed to toggle channel: {e}")
        raise HTTPException(status_code=500, detail=str(e))
