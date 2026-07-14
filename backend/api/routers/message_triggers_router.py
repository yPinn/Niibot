"""Message trigger configuration API routes."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import sys
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.dependencies import get_current_channel_id, get_trigger_service, require_activated
from services.message_trigger_service import MessageTriggerService

_REGEX_MAX_LEN = 200
_REDOS_CANARY = "a" * 30 + "b"
_REDOS_TIMEOUT = 1.5

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/triggers", tags=["triggers"])


def _redos_safe(pattern: str) -> bool:
    """Run pattern against a canary in a subprocess. Returns True if safe (no timeout)."""
    env = {**os.environ, "_NII_PATTERN": pattern, "_NII_CANARY": _REDOS_CANARY}
    code = "import re, os; re.search(os.environ['_NII_PATTERN'], os.environ['_NII_CANARY'])"
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            timeout=_REDOS_TIMEOUT,
            capture_output=True,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False


class MessageTriggerResponse(BaseModel):
    id: int
    channel_id: str
    trigger_name: str
    match_type: str
    pattern: str
    case_sensitive: bool
    response: str
    min_role: str
    cooldown: int | None
    priority: int
    enabled: bool
    usage_count: int = 0
    aliases: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TriggerCreate(BaseModel):
    trigger_name: str
    match_type: str = "startswith"
    pattern: str
    case_sensitive: bool = False
    response: str
    min_role: str = "everyone"
    cooldown: int | None = None
    priority: int = Field(default=0, ge=0, le=100)
    aliases: str | None = None


class TriggerUpdate(BaseModel):
    match_type: str | None = None
    pattern: str | None = None
    case_sensitive: bool | None = None
    response: str | None = None
    min_role: str | None = None
    cooldown: int | None = None
    priority: int | None = None
    enabled: bool | None = None
    aliases: str | None = None


class TriggerToggle(BaseModel):
    enabled: bool


async def _validate_regex_pattern(pattern: str, match_type: str) -> None:
    """Reject patterns that are too long, syntactically invalid, or trigger ReDoS."""
    if match_type != "regex":
        return
    if len(pattern) > _REGEX_MAX_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Regex pattern exceeds maximum length of {_REGEX_MAX_LEN} characters",
        )
    try:
        re.compile(pattern)
    except re.error as exc:
        raise HTTPException(status_code=400, detail=f"Invalid regex pattern: {exc}") from exc
    loop = asyncio.get_running_loop()
    safe = await loop.run_in_executor(None, _redos_safe, pattern)
    if not safe:
        raise HTTPException(status_code=400, detail="Regex pattern is unsafe (potential ReDoS)")


@router.get("/configs", response_model=list[MessageTriggerResponse])
async def get_trigger_configs(
    channel_id: str = Depends(get_current_channel_id),
    service: MessageTriggerService = Depends(get_trigger_service),
    _: None = Depends(require_activated),
) -> list[MessageTriggerResponse]:
    """Get all message triggers for the authenticated user's channel."""
    try:
        triggers = await service.list_triggers(channel_id)
        return [MessageTriggerResponse(**t) for t in triggers]
    except Exception:
        LOGGER.exception("Failed to get trigger configs")
        raise HTTPException(status_code=500, detail="Failed to fetch trigger configs") from None


@router.post("/configs", response_model=MessageTriggerResponse, status_code=201)
async def create_trigger(
    body: TriggerCreate,
    channel_id: str = Depends(get_current_channel_id),
    service: MessageTriggerService = Depends(get_trigger_service),
    _: None = Depends(require_activated),
) -> MessageTriggerResponse:
    """Create a new message trigger."""
    await _validate_regex_pattern(body.pattern, body.match_type)
    try:
        trigger = await service.create_trigger(
            channel_id,
            body.trigger_name,
            match_type=body.match_type,
            pattern=body.pattern,
            case_sensitive=body.case_sensitive,
            response=body.response,
            min_role=body.min_role,
            cooldown=body.cooldown,
            priority=body.priority,
            aliases=body.aliases or None,
        )
        LOGGER.info("Channel %s created trigger: %s", channel_id, body.trigger_name)
        return MessageTriggerResponse(**trigger)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception:
        LOGGER.exception("Failed to create trigger")
        raise HTTPException(status_code=500, detail="Failed to create trigger") from None


@router.put("/configs/{trigger_name}", response_model=MessageTriggerResponse)
async def update_trigger(
    trigger_name: str,
    body: TriggerUpdate,
    channel_id: str = Depends(get_current_channel_id),
    service: MessageTriggerService = Depends(get_trigger_service),
    _: None = Depends(require_activated),
) -> MessageTriggerResponse:
    """Update a message trigger's settings."""
    try:
        if body.pattern is not None:
            effective_match_type = body.match_type
            if effective_match_type is None:
                existing = await service.get_trigger(channel_id, trigger_name)
                effective_match_type = (
                    existing.get("match_type", "contains") if existing else "contains"
                )
            await _validate_regex_pattern(body.pattern, effective_match_type)
        trigger = await service.update_trigger(
            channel_id,
            trigger_name,
            match_type=body.match_type,
            pattern=body.pattern,
            case_sensitive=body.case_sensitive,
            response=body.response,
            min_role=body.min_role,
            cooldown=body.cooldown,
            priority=body.priority,
            enabled=body.enabled,
            aliases=body.aliases,
        )
        if trigger is None:
            raise HTTPException(status_code=404, detail="Trigger not found")
        LOGGER.info("Channel %s updated trigger: %s", channel_id, trigger_name)
        return MessageTriggerResponse(**trigger)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception:
        LOGGER.exception("Failed to update trigger")
        raise HTTPException(status_code=500, detail="Failed to update trigger") from None


@router.patch("/configs/{trigger_name}/toggle", response_model=MessageTriggerResponse)
async def toggle_trigger(
    trigger_name: str,
    body: TriggerToggle,
    channel_id: str = Depends(get_current_channel_id),
    service: MessageTriggerService = Depends(get_trigger_service),
    _: None = Depends(require_activated),
) -> MessageTriggerResponse:
    """Toggle a trigger's enabled state."""
    try:
        trigger = await service.toggle_trigger(channel_id, trigger_name, body.enabled)
        if trigger is None:
            raise HTTPException(status_code=404, detail="Trigger not found")
        LOGGER.info("Channel %s toggled trigger: %s -> %s", channel_id, trigger_name, body.enabled)
        return MessageTriggerResponse(**trigger)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to toggle trigger")
        raise HTTPException(status_code=500, detail="Failed to toggle trigger") from None


@router.delete("/configs/{trigger_name}", status_code=204)
async def delete_trigger(
    trigger_name: str,
    channel_id: str = Depends(get_current_channel_id),
    service: MessageTriggerService = Depends(get_trigger_service),
    _: None = Depends(require_activated),
) -> None:
    """Delete a message trigger."""
    try:
        deleted = await service.delete_trigger(channel_id, trigger_name)
        if not deleted:
            raise HTTPException(status_code=404, detail="Trigger not found")
        LOGGER.info("Channel %s deleted trigger: %s", channel_id, trigger_name)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to delete trigger")
        raise HTTPException(status_code=500, detail="Failed to delete trigger") from None
