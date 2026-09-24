"""Authenticated, tenant-scoped stream schedule routes.

CRUD for stream_schedule_settings / stream_schedules / stream_schedule_segments.
Auto-apply itself lives in twitch/components/stream_schedule_manager.py — this
router only manages the data the bot reads from.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.dependencies import (
    get_stream_schedule_service,
    get_twitch_api,
    require_self_tenant_access,
)
from services.tenant_service import TenantContext
from services.twitch_api import TwitchAPIClient
from shared.errors import InvalidInputError, NotFoundError
from shared.models.stream_schedule import ScheduleKind
from shared.services.stream_schedule_service import StreamScheduleService

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stream-schedule", tags=["stream-schedule"])


class StreamScheduleInvalidError(InvalidInputError):
    code = "STREAM_SCHEDULE.INVALID"
    user_message = "排程設定內容無效，請檢查後再試"


class StreamScheduleNotFoundError(NotFoundError):
    code = "STREAM_SCHEDULE.NOT_FOUND"
    user_message = "找不到這筆排程"


class StreamScheduleSegmentNotFoundError(NotFoundError):
    code = "STREAM_SCHEDULE_SEGMENT.NOT_FOUND"
    user_message = "找不到這個排程區塊"


class StreamScheduleGameSearchResult(BaseModel):
    id: str
    name: str
    box_art_url: str | None = None


class StreamScheduleSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel_id: str
    timezone: str
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StreamScheduleSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    enabled: bool | None = None


class StreamScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: str
    kind: ScheduleKind
    weekday: int | None
    specific_date: date | None
    start_time: time
    duration_minutes: int
    title_template: str
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StreamScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ScheduleKind
    weekday: int | None = Field(default=None, ge=0, le=6)
    specific_date: date | None = None
    start_time: time
    duration_minutes: int = Field(ge=1, le=1440)
    title_template: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_kind_fields(self) -> StreamScheduleCreate:
        if self.kind is ScheduleKind.RECURRING:
            if self.weekday is None or self.specific_date is not None:
                raise ValueError("recurring schedules require weekday and no specific_date")
        else:
            if self.specific_date is None or self.weekday is not None:
                raise ValueError("one-off schedules require specific_date and no weekday")
        return self


class StreamScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_time: time | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    title_template: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None


class StreamScheduleSegmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: str
    schedule_id: int
    offset_minutes: int
    title_template: str
    game_id: str | None
    game_name: str | None
    sort_order: int


class StreamScheduleSegmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offset_minutes: int = Field(ge=0, le=1440)
    title_template: str = Field(default="", max_length=500)
    # Pre-resolved from GET /games/search — the frontend's picker already
    # confirmed this is a real Twitch category, so no server-side re-resolution.
    # Both unset means no game for this segment.
    game_id: str | None = Field(default=None, max_length=64)
    game_name: str | None = Field(default=None, max_length=200)
    sort_order: int = 0

    @model_validator(mode="after")
    def validate_game_pair(self) -> StreamScheduleSegmentCreate:
        if (self.game_id is None) != (self.game_name is None):
            raise ValueError("game_id and game_name must be provided together")
        return self


class StreamScheduleSegmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offset_minutes: int | None = Field(default=None, ge=0, le=1440)
    title_template: str | None = Field(default=None, max_length=500)
    # None (both fields) = leave the segment's game unchanged; "" (both fields)
    # = explicitly clear it; matching non-empty values = set to that game.
    game_id: str | None = Field(default=None, max_length=64)
    game_name: str | None = Field(default=None, max_length=200)
    sort_order: int | None = None

    @model_validator(mode="after")
    def validate_game_pair(self) -> StreamScheduleSegmentUpdate:
        def state(v: str | None) -> str:
            return "unset" if v is None else "cleared" if v == "" else "set"

        if state(self.game_id) != state(self.game_name):
            raise ValueError(
                'game_id and game_name must both be unset, both cleared (""), or both set together'
            )
        return self


# ----------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------


@router.get("/settings", response_model=StreamScheduleSettingsResponse)
async def get_stream_schedule_settings(
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: StreamScheduleService = Depends(get_stream_schedule_service),
) -> StreamScheduleSettingsResponse:
    settings = await service.get_settings(tenant.channel_id)
    return StreamScheduleSettingsResponse.model_validate(settings)


@router.patch("/settings", response_model=StreamScheduleSettingsResponse)
async def update_stream_schedule_settings(
    body: StreamScheduleSettingsUpdate,
    _action: Literal["stream-schedule-settings"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: StreamScheduleService = Depends(get_stream_schedule_service),
) -> StreamScheduleSettingsResponse:
    try:
        settings = await service.update_settings(
            tenant.channel_id, timezone=body.timezone, enabled=body.enabled
        )
    except ValueError:
        LOGGER.info("stream_schedule_settings_validation_failed")
        raise StreamScheduleInvalidError() from None
    LOGGER.info("stream_schedule_settings_updated")
    return StreamScheduleSettingsResponse.model_validate(settings)


# ----------------------------------------------------------------------
# Schedules (plan level)
# ----------------------------------------------------------------------


@router.get("/schedules", response_model=list[StreamScheduleResponse])
async def list_stream_schedules(
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: StreamScheduleService = Depends(get_stream_schedule_service),
) -> list[StreamScheduleResponse]:
    schedules = await service.list_schedules(tenant.channel_id)
    return [StreamScheduleResponse.model_validate(s) for s in schedules]


@router.post("/schedules", response_model=StreamScheduleResponse, status_code=201)
async def create_stream_schedule(
    body: StreamScheduleCreate,
    _action: Literal["stream-schedule-create"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: StreamScheduleService = Depends(get_stream_schedule_service),
) -> StreamScheduleResponse:
    try:
        schedule = await service.create_schedule(
            tenant.channel_id,
            kind=body.kind,
            weekday=body.weekday,
            specific_date=body.specific_date,
            start_time=body.start_time,
            duration_minutes=body.duration_minutes,
            title_template=body.title_template,
        )
    except ValueError:
        LOGGER.info("stream_schedule_create_validation_failed")
        raise StreamScheduleInvalidError() from None
    LOGGER.info("stream_schedule_created", extra={"schedule_id": schedule.id})
    return StreamScheduleResponse.model_validate(schedule)


@router.put("/schedules/{schedule_id}", response_model=StreamScheduleResponse)
async def update_stream_schedule(
    schedule_id: int,
    body: StreamScheduleUpdate,
    _action: Literal["stream-schedule-update"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: StreamScheduleService = Depends(get_stream_schedule_service),
) -> StreamScheduleResponse:
    schedule = await service.update_schedule(
        tenant.channel_id,
        schedule_id,
        start_time=body.start_time,
        duration_minutes=body.duration_minutes,
        title_template=body.title_template,
        enabled=body.enabled,
    )
    if schedule is None:
        raise StreamScheduleNotFoundError(context={"schedule_id": schedule_id})
    LOGGER.info("stream_schedule_updated", extra={"schedule_id": schedule_id})
    return StreamScheduleResponse.model_validate(schedule)


@router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_stream_schedule(
    schedule_id: int,
    _action: Literal["stream-schedule-delete"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: StreamScheduleService = Depends(get_stream_schedule_service),
) -> None:
    deleted = await service.delete_schedule(tenant.channel_id, schedule_id)
    if not deleted:
        raise StreamScheduleNotFoundError(context={"schedule_id": schedule_id})
    LOGGER.info("stream_schedule_deleted", extra={"schedule_id": schedule_id})


# ----------------------------------------------------------------------
# Segments (sub-blocks of a schedule)
# ----------------------------------------------------------------------


@router.get("/games/search", response_model=list[StreamScheduleGameSearchResult])
async def search_stream_schedule_games(
    q: str = Query(min_length=1, max_length=100),
    tenant: TenantContext = Depends(require_self_tenant_access),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> list[StreamScheduleGameSearchResult]:
    """Fuzzy category search backing the segment editor's game picker — same
    Helix endpoint Twitch's own category picker uses (unlike get_games_by_names,
    which requires an exact name and is only kept for the !game chat command)."""
    results = await twitch_api.search_categories(q)
    return [
        StreamScheduleGameSearchResult(id=r["id"], name=r["name"], box_art_url=r.get("box_art_url"))
        for r in results
    ]


@router.get("/schedules/{schedule_id}/segments", response_model=list[StreamScheduleSegmentResponse])
async def list_stream_schedule_segments(
    schedule_id: int,
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: StreamScheduleService = Depends(get_stream_schedule_service),
) -> list[StreamScheduleSegmentResponse]:
    segments = await service.list_segments(tenant.channel_id, schedule_id)
    return [StreamScheduleSegmentResponse.model_validate(s) for s in segments]


@router.post(
    "/schedules/{schedule_id}/segments",
    response_model=StreamScheduleSegmentResponse,
    status_code=201,
)
async def create_stream_schedule_segment(
    schedule_id: int,
    body: StreamScheduleSegmentCreate,
    _action: Literal["stream-schedule-segment-create"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: StreamScheduleService = Depends(get_stream_schedule_service),
) -> StreamScheduleSegmentResponse:
    segment = await service.add_segment(
        tenant.channel_id,
        schedule_id,
        offset_minutes=body.offset_minutes,
        title_template=body.title_template,
        game_id=body.game_id,
        game_name=body.game_name,
        sort_order=body.sort_order,
    )
    if segment is None:
        raise StreamScheduleNotFoundError(context={"schedule_id": schedule_id})
    LOGGER.info("stream_schedule_segment_created", extra={"segment_id": segment.id})
    return StreamScheduleSegmentResponse.model_validate(segment)


@router.put("/segments/{segment_id}", response_model=StreamScheduleSegmentResponse)
async def update_stream_schedule_segment(
    segment_id: int,
    body: StreamScheduleSegmentUpdate,
    _action: Literal["stream-schedule-segment-update"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: StreamScheduleService = Depends(get_stream_schedule_service),
) -> StreamScheduleSegmentResponse:
    clear_game = body.game_id == ""
    segment = await service.update_segment(
        tenant.channel_id,
        segment_id,
        offset_minutes=body.offset_minutes,
        title_template=body.title_template,
        game_id=body.game_id or None,
        game_name=body.game_name or None,
        sort_order=body.sort_order,
        clear_game=clear_game,
    )
    if segment is None:
        raise StreamScheduleSegmentNotFoundError(context={"segment_id": segment_id})
    LOGGER.info("stream_schedule_segment_updated", extra={"segment_id": segment_id})
    return StreamScheduleSegmentResponse.model_validate(segment)


@router.delete("/segments/{segment_id}", status_code=204)
async def delete_stream_schedule_segment(
    segment_id: int,
    _action: Literal["stream-schedule-segment-delete"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: StreamScheduleService = Depends(get_stream_schedule_service),
) -> None:
    deleted = await service.delete_segment(tenant.channel_id, segment_id)
    if not deleted:
        raise StreamScheduleSegmentNotFoundError(context={"segment_id": segment_id})
    LOGGER.info("stream_schedule_segment_deleted", extra={"segment_id": segment_id})
