"""Command configuration API routes"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.constants import VALID_ROLES
from core.dependencies import (
    get_command_config_service,
    get_current_channel_id,
    get_twitch_api,
    require_activated,
    require_self_tenant_access,
)
from services import CommandConfigService, TenantContext, TwitchAPIClient
from shared.cache import AsyncTTLCache
from shared.repositories.command_config import UNSET as _UNSET

# Cache username → user_info for 60 s to avoid a Twitch API call on every page load
_user_lookup_cache: AsyncTTLCache = AsyncTTLCache(maxsize=256, ttl=60.0)

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/commands", tags=["commands"])


class CommandConfigResponse(BaseModel):
    id: int | None
    channel_id: str
    command_name: str
    command_type: str
    enabled: bool
    custom_response: str | None = None
    cooldown: int | None = None
    min_role: str
    aliases: str | None = None
    usage_count: int
    description: str = ""
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


@router.get("/configs", response_model=list[CommandConfigResponse])
async def get_command_configs(
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    service: CommandConfigService = Depends(get_command_config_service),
) -> list[CommandConfigResponse]:
    """Get all command configs for the authenticated user's channel."""
    try:
        configs = await service.list_commands(channel_id)
        return [CommandConfigResponse(**cfg) for cfg in configs]
    except Exception:
        LOGGER.exception("Failed to get command configs")
        raise HTTPException(status_code=500, detail="Failed to fetch command configs") from None


@router.post("/configs", response_model=CommandConfigResponse, status_code=201)
async def create_custom_command(
    body: CustomCommandCreate,
    _: None = Depends(require_activated),
    ctx: TenantContext = Depends(require_self_tenant_access),
    service: CommandConfigService = Depends(get_command_config_service),
) -> CommandConfigResponse:
    """Create a new custom command.

    Exemplar for the new tenant-access dependency on a write endpoint.
    Other endpoints in this file still use ``get_current_channel_id`` (the
    legacy shim) and can be migrated incrementally — both dependencies
    return the caller's channel today, but only ``require_self_tenant_access``
    enforces channel_members membership, which matters once mod delegation
    or tenant suspension is enabled.
    """
    channel_id = ctx.channel_id
    if body.min_role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid min_role: {body.min_role}")
    if not body.custom_response:
        raise HTTPException(status_code=400, detail="custom_response is required")
    try:
        cfg = await service.create_custom_command(
            channel_id,
            body.command_name,
            custom_response=body.custom_response,
            cooldown=body.cooldown,
            min_role=body.min_role,
            aliases=body.aliases,
        )
        LOGGER.info("Channel %s created custom command: %s", channel_id, body.command_name)
        return CommandConfigResponse(**cfg)
    except Exception:
        LOGGER.exception("Failed to create custom command")
        raise HTTPException(status_code=500, detail="Failed to create custom command") from None


@router.put("/configs/{command_name}", response_model=CommandConfigResponse)
async def update_command_config(
    command_name: str,
    body: CommandConfigUpdate,
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    service: CommandConfigService = Depends(get_command_config_service),
) -> CommandConfigResponse:
    """Update a command config."""
    if body.min_role is not None and body.min_role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid min_role: {body.min_role}")
    try:
        cfg = await service.update_command(
            channel_id,
            command_name,
            enabled=body.enabled,
            custom_response=body.custom_response,
            cooldown=body.cooldown if "cooldown" in body.model_fields_set else _UNSET,
            min_role=body.min_role,
            aliases=body.aliases,
        )
        if cfg is None:
            raise HTTPException(status_code=404, detail="Command not found")
        LOGGER.info("Channel %s updated command config: %s", channel_id, command_name)
        return CommandConfigResponse(**cfg)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to update command config")
        raise HTTPException(status_code=500, detail="Failed to update command config") from None


@router.patch("/configs/{command_name}/toggle", response_model=CommandConfigResponse)
async def toggle_command_config(
    command_name: str,
    body: CommandConfigToggle,
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    service: CommandConfigService = Depends(get_command_config_service),
) -> CommandConfigResponse:
    """Toggle a command's enabled state."""
    try:
        cfg = await service.toggle_command(channel_id, command_name, body.enabled)
        if cfg is None:
            raise HTTPException(status_code=404, detail="Command not found")
        LOGGER.info("Channel %s toggled command: %s -> %s", channel_id, command_name, body.enabled)
        return CommandConfigResponse(**cfg)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to toggle command config")
        raise HTTPException(status_code=500, detail="Failed to toggle command config") from None


@router.delete("/configs/{command_name}", status_code=204)
async def delete_custom_command(
    command_name: str,
    _: None = Depends(require_activated),
    channel_id: str = Depends(get_current_channel_id),
    service: CommandConfigService = Depends(get_command_config_service),
) -> None:
    """Delete a custom command (only custom type)."""
    try:
        deleted = await service.delete_custom_command(channel_id, command_name)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail="Custom command not found or cannot delete builtin commands",
            )
        LOGGER.info("Channel %s deleted custom command: %s", channel_id, command_name)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to delete custom command")
        raise HTTPException(status_code=500, detail="Failed to delete custom command") from None


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
    service: CommandConfigService = Depends(get_command_config_service),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> PublicCommandsResponse:
    """Get enabled commands for a channel (public, no auth).

    Uses Twitch API to resolve login name → user_id + profile,
    then queries command_configs by channel_id directly.
    No dependency on channels.channel_name.
    """
    try:
        cache_key = f"user_by_login:{username.lower()}"
        if cache_key in _user_lookup_cache:
            user_info = _user_lookup_cache.get(cache_key)
        else:
            user_info = await twitch_api.get_user_by_login(username)
            if user_info:
                _user_lookup_cache.set(cache_key, user_info)
        if not user_info:
            raise HTTPException(status_code=404, detail="Channel not found")

        channel_id = user_info["id"]
        profile = PublicChannelProfile(
            display_name=user_info.get("display_name"),
            profile_image_url=user_info.get("avatar"),
        )

        commands = await service.list_public_commands(channel_id)

        return PublicCommandsResponse(
            channel=profile,
            commands=[PublicCommandItem(**cmd) for cmd in commands],
        )
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to get public commands")
        raise HTTPException(status_code=500, detail="Failed to fetch commands") from None
