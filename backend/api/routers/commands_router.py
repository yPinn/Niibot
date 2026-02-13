"""Command configuration API routes"""

import logging
from datetime import datetime

from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.dependencies import get_current_channel_id, get_db_pool, get_twitch_api
from services import CommandConfigService, TwitchAPIClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/commands", tags=["commands"])


# ============================================
# Response / Request Models
# ============================================

VALID_ROLES = {"everyone", "subscriber", "vip", "moderator", "broadcaster"}


class CommandConfigResponse(BaseModel):
    id: int
    channel_id: str
    command_name: str
    command_type: str
    enabled: bool
    custom_response: str | None = None
    cooldown: int | None = None
    min_role: str
    aliases: str | None = None
    usage_count: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CommandConfigUpdate(BaseModel):
    enabled: bool | None = None
    custom_response: str | None = None
    cooldown: int | None = None
    min_role: str | None = None
    aliases: str | None = None


class CommandConfigToggle(BaseModel):
    enabled: bool


class CustomCommandCreate(BaseModel):
    command_name: str
    custom_response: str | None = None
    cooldown: int | None = None
    min_role: str = "everyone"
    aliases: str | None = None


# ============================================
# Command Config Endpoints
# ============================================


@router.get("/configs", response_model=list[CommandConfigResponse])
async def get_command_configs(
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> list[CommandConfigResponse]:
    """Get all command configs for the authenticated user's channel."""
    try:
        service = CommandConfigService(pool)
        configs = await service.list_commands(channel_id)
        return [CommandConfigResponse(**cfg) for cfg in configs]
    except Exception as e:
        logger.exception(f"Failed to get command configs: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch command configs") from None


@router.post("/configs", response_model=CommandConfigResponse, status_code=201)
async def create_custom_command(
    body: CustomCommandCreate,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> CommandConfigResponse:
    """Create a new custom command."""
    if body.min_role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid min_role: {body.min_role}")
    if not body.custom_response:
        raise HTTPException(status_code=400, detail="custom_response is required")
    try:
        service = CommandConfigService(pool)
        cfg = await service.create_custom_command(
            channel_id,
            body.command_name,
            custom_response=body.custom_response,
            cooldown=body.cooldown,
            min_role=body.min_role,
            aliases=body.aliases,
        )
        logger.info(f"Channel {channel_id} created custom command: {body.command_name}")
        return CommandConfigResponse(**cfg)
    except Exception as e:
        logger.exception(f"Failed to create custom command: {e}")
        raise HTTPException(status_code=500, detail="Failed to create custom command") from None


@router.put("/configs/{command_name}", response_model=CommandConfigResponse)
async def update_command_config(
    command_name: str,
    body: CommandConfigUpdate,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> CommandConfigResponse:
    """Update a command config."""
    if body.min_role is not None and body.min_role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid min_role: {body.min_role}")
    try:
        service = CommandConfigService(pool)
        cfg = await service.update_command(
            channel_id,
            command_name,
            enabled=body.enabled,
            custom_response=body.custom_response,
            cooldown=body.cooldown,
            min_role=body.min_role,
            aliases=body.aliases,
        )
        logger.info(f"Channel {channel_id} updated command config: {command_name}")
        return CommandConfigResponse(**cfg)
    except Exception as e:
        logger.exception(f"Failed to update command config: {e}")
        raise HTTPException(status_code=500, detail="Failed to update command config") from None


@router.patch("/configs/{command_name}/toggle", response_model=CommandConfigResponse)
async def toggle_command_config(
    command_name: str,
    body: CommandConfigToggle,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> CommandConfigResponse:
    """Toggle a command's enabled state."""
    try:
        service = CommandConfigService(pool)
        cfg = await service.toggle_command(channel_id, command_name, body.enabled)
        logger.info(f"Channel {channel_id} toggled command: {command_name} -> {body.enabled}")
        return CommandConfigResponse(**cfg)
    except Exception as e:
        logger.exception(f"Failed to toggle command config: {e}")
        raise HTTPException(status_code=500, detail="Failed to toggle command config") from None


@router.delete("/configs/{command_name}", status_code=204)
async def delete_custom_command(
    command_name: str,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> None:
    """Delete a custom command (only custom type)."""
    try:
        service = CommandConfigService(pool)
        deleted = await service.delete_custom_command(channel_id, command_name)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail="Custom command not found or cannot delete builtin commands",
            )
        logger.info(f"Channel {channel_id} deleted custom command: {command_name}")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete custom command: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete custom command") from None


# ============================================
# Public Endpoints (no auth required)
# ============================================


class PublicCommandItem(BaseModel):
    name: str
    description: str
    min_role: str = "everyone"
    command_type: str = "builtin"


class PublicChannelProfile(BaseModel):
    display_name: str | None = None
    profile_image_url: str | None = None


class PublicCommandsResponse(BaseModel):
    channel: PublicChannelProfile
    commands: list[PublicCommandItem]


@router.get("/public/{username}", response_model=PublicCommandsResponse)
async def get_public_commands(
    username: str,
    pool: Pool = Depends(get_db_pool),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> PublicCommandsResponse:
    """Get enabled commands for a channel (public, no auth).

    Uses Twitch API to resolve login name → user_id + profile,
    then queries command_configs by channel_id directly.
    No dependency on channels.channel_name.
    """
    try:
        # 1. Resolve login name via Twitch API (also gives profile)
        user_info = await twitch_api.get_user_by_login(username)
        if not user_info:
            raise HTTPException(status_code=404, detail="Channel not found")

        channel_id = user_info["id"]
        profile = PublicChannelProfile(
            display_name=user_info.get("display_name"),
            profile_image_url=user_info.get("avatar"),
        )

        # 2. Fetch enabled commands by channel_id
        service = CommandConfigService(pool)
        commands = await service.list_public_commands(channel_id)

        return PublicCommandsResponse(
            channel=profile,
            commands=[PublicCommandItem(**cmd) for cmd in commands],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get public commands: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch commands") from None
