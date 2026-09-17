"""Message trigger configuration API routes."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.constants import MAX_RESPONSE_LENGTH
from core.dependencies import get_current_channel_id, get_trigger_service, require_activated
from services.message_trigger_service import MessageTriggerService
from shared.errors import InvalidInputError, NotFoundError
from shared.trigger_matching import validate_regex_pattern

_REGEX_MAX_LEN = 200

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/triggers", tags=["triggers"])


class TriggerNotFoundError(NotFoundError):
    code = "TRIGGER.NOT_FOUND"
    user_message = "找不到這個觸發詞"


class TriggerInvalidError(InvalidInputError):
    code = "TRIGGER.INVALID"
    user_message = "觸發詞的設定有誤，請檢查後再試"


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
    response: str = Field(max_length=MAX_RESPONSE_LENGTH)
    min_role: str = "everyone"
    cooldown: int | None = None
    priority: int = Field(default=0, ge=0, le=100)
    aliases: str | None = None


class TriggerUpdate(BaseModel):
    match_type: str | None = None
    pattern: str | None = None
    case_sensitive: bool | None = None
    response: str | None = Field(default=None, max_length=MAX_RESPONSE_LENGTH)
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
        raise TriggerInvalidError(
            user_message=f"正規表達式太長了，上限 {_REGEX_MAX_LEN} 個字元",
            context={"pattern_len": len(pattern)},
        )
    try:
        re.compile(pattern)
    except re.error as exc:
        raise TriggerInvalidError(
            user_message="正規表達式語法有誤", context={"regex_error": str(exc)}
        ) from exc
    loop = asyncio.get_running_loop()
    safe = await loop.run_in_executor(None, validate_regex_pattern, pattern)
    if not safe:
        raise TriggerInvalidError(user_message="這個正規表達式可能造成效能問題，請簡化")


@router.get("/configs", response_model=list[MessageTriggerResponse])
async def get_trigger_configs(
    channel_id: str = Depends(get_current_channel_id),
    service: MessageTriggerService = Depends(get_trigger_service),
    _: None = Depends(require_activated),
) -> list[MessageTriggerResponse]:
    """Get all message triggers for the authenticated user's channel."""
    triggers = await service.list_triggers(channel_id)
    return [MessageTriggerResponse(**t) for t in triggers]


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
    except ValueError as e:
        raise TriggerInvalidError(context={"reason": str(e)}) from e
    LOGGER.info("trigger_created", extra={"trigger_name": body.trigger_name})
    return MessageTriggerResponse(**trigger)


@router.put("/configs/{trigger_name}", response_model=MessageTriggerResponse)
async def update_trigger(
    trigger_name: str,
    body: TriggerUpdate,
    channel_id: str = Depends(get_current_channel_id),
    service: MessageTriggerService = Depends(get_trigger_service),
    _: None = Depends(require_activated),
) -> MessageTriggerResponse:
    """Update a message trigger's settings."""
    if body.pattern is not None:
        effective_match_type = body.match_type
        if effective_match_type is None:
            existing = await service.get_trigger(channel_id, trigger_name)
            effective_match_type = (
                existing.get("match_type", "contains") if existing else "contains"
            )
        await _validate_regex_pattern(body.pattern, effective_match_type)
    try:
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
    except ValueError as e:
        raise TriggerInvalidError(context={"reason": str(e)}) from e
    if trigger is None:
        raise TriggerNotFoundError(context={"trigger_name": trigger_name})
    LOGGER.info("trigger_updated", extra={"trigger_name": trigger_name})
    return MessageTriggerResponse(**trigger)


@router.patch("/configs/{trigger_name}/toggle", response_model=MessageTriggerResponse)
async def toggle_trigger(
    trigger_name: str,
    body: TriggerToggle,
    channel_id: str = Depends(get_current_channel_id),
    service: MessageTriggerService = Depends(get_trigger_service),
    _: None = Depends(require_activated),
) -> MessageTriggerResponse:
    """Toggle a trigger's enabled state."""
    trigger = await service.toggle_trigger(channel_id, trigger_name, body.enabled)
    if trigger is None:
        raise TriggerNotFoundError(context={"trigger_name": trigger_name})
    LOGGER.info("trigger_toggled", extra={"trigger_name": trigger_name, "enabled": body.enabled})
    return MessageTriggerResponse(**trigger)


@router.delete("/configs/{trigger_name}", status_code=204)
async def delete_trigger(
    trigger_name: str,
    channel_id: str = Depends(get_current_channel_id),
    service: MessageTriggerService = Depends(get_trigger_service),
    _: None = Depends(require_activated),
) -> None:
    """Delete a message trigger."""
    deleted = await service.delete_trigger(channel_id, trigger_name)
    if not deleted:
        raise TriggerNotFoundError(context={"trigger_name": trigger_name})
    LOGGER.info("trigger_deleted", extra={"trigger_name": trigger_name})
