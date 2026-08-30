"""Public community event feed and tenant-owned overlay access settings."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.dependencies import get_community_overlay_service, require_self_tenant_access
from core.rate_limit import RateLimiter
from services.tenant_service import TenantContext
from shared.community_overlay_themes import validate_overlay_theme
from shared.errors import NotFoundError
from shared.models.attendance import CommunityOverlayThemePublished, CommunityOverlayThemeState
from shared.services.community_overlay import CommunityOverlayService

router = APIRouter(prefix="/api/community-overlay", tags=["community-overlay"])
_feed_limiter = RateLimiter(max_calls=240, period=60.0)
_public_theme_limiter = RateLimiter(max_calls=120, period=60.0)
_public_ip_limiter = RateLimiter(max_calls=600, period=60.0)


class CommunityOverlayNotFoundError(NotFoundError):
    code = "COMMUNITY_OVERLAY.NOT_FOUND"
    user_message = "找不到這個顯示來源"


class OverlayEventResponse(BaseModel):
    id: int
    event_type: str
    schema_version: int
    source: str
    actor_display_name: str | None
    payload: dict
    occurred_at: datetime
    expires_at: datetime | None


class OverlayFeedResponse(BaseModel):
    cursor: int
    events: list[OverlayEventResponse]


class OverlayAccessResponse(BaseModel):
    public_key: UUID
    enabled: bool
    created_at: datetime
    updated_at: datetime


class OverlayAccessUpdate(BaseModel):
    enabled: bool


class OverlayThemeDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    surface_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    accent_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    text_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    placement: Literal["top-left", "top-right", "bottom-left", "bottom-right"]
    radius_px: int = Field(ge=0, le=40)
    display_ms: int = Field(ge=2_000, le=15_000)
    motion: Literal["standard", "subtle", "none"]

    @model_validator(mode="after")
    def validate_renderer_contract(self) -> OverlayThemeDefinition:
        validate_overlay_theme(self.model_dump())
        return self


class OverlayThemeDraftUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme: OverlayThemeDefinition
    expected_draft_version: int = Field(strict=True, ge=1)


class OverlayThemeActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_draft_version: int = Field(strict=True, ge=1)


class OverlayThemePublishedResponse(BaseModel):
    revision_id: int | None
    renderer: str
    schema_version: int
    theme: OverlayThemeDefinition
    created_at: datetime | None


class OverlayThemeStateResponse(BaseModel):
    renderer: str
    schema_version: int
    draft_version: int
    draft: OverlayThemeDefinition
    published: OverlayThemePublishedResponse
    has_unpublished_changes: bool
    updated_at: datetime


def _published_theme_response(
    published: CommunityOverlayThemePublished,
) -> OverlayThemePublishedResponse:
    return OverlayThemePublishedResponse(
        revision_id=published.revision_id,
        renderer=published.renderer,
        schema_version=published.schema_version,
        theme=OverlayThemeDefinition.model_validate(published.theme),
        created_at=published.created_at,
    )


def _public_key_from_header(request: Request, raw_key: str) -> UUID:
    client_host = request.client.host if request.client else "unknown"
    _public_ip_limiter.require(client_host)
    try:
        return UUID(raw_key)
    except ValueError:
        raise CommunityOverlayNotFoundError() from None


def _protect_capability_response(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


def _theme_state_response(state: CommunityOverlayThemeState) -> OverlayThemeStateResponse:
    return OverlayThemeStateResponse(
        renderer=state.renderer,
        schema_version=state.schema_version,
        draft_version=state.draft_version,
        draft=OverlayThemeDefinition.model_validate(state.draft_theme),
        published=_published_theme_response(state.published),
        has_unpublished_changes=state.has_unpublished_changes,
        updated_at=state.updated_at,
    )


@router.get("/public/events", response_model=OverlayFeedResponse)
async def get_public_feed(
    request: Request,
    response: Response,
    overlay_key: str = Header(alias="X-Overlay-Key"),
    after_id: int | None = Query(default=None, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    service: CommunityOverlayService = Depends(get_community_overlay_service),
) -> OverlayFeedResponse:
    """Read an ordered, reconnect-safe event page using a rotatable public key."""
    public_key = _public_key_from_header(request, overlay_key)
    client_host = request.client.host if request.client else "unknown"
    _feed_limiter.require(f"{client_host}:{public_key}")
    feed = await service.get_feed(public_key, after_id=after_id, limit=limit)
    if feed is None:
        raise CommunityOverlayNotFoundError()
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return OverlayFeedResponse(
        cursor=feed.cursor,
        events=[OverlayEventResponse(**asdict(event)) for event in feed.events],
    )


@router.get("/public/theme", response_model=OverlayThemePublishedResponse)
async def get_public_theme(
    request: Request,
    response: Response,
    overlay_key: str = Header(alias="X-Overlay-Key"),
    service: CommunityOverlayService = Depends(get_community_overlay_service),
) -> OverlayThemePublishedResponse:
    """Return only the published renderer snapshot for a valid capability key."""
    public_key = _public_key_from_header(request, overlay_key)
    client_host = request.client.host if request.client else "unknown"
    _public_theme_limiter.require(f"{client_host}:{public_key}")
    published = await service.get_public_theme(public_key)
    if published is None:
        raise CommunityOverlayNotFoundError()
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return _published_theme_response(published)


@router.get("/settings", response_model=OverlayAccessResponse)
async def get_overlay_access(
    response: Response,
    ctx: TenantContext = Depends(require_self_tenant_access),
    service: CommunityOverlayService = Depends(get_community_overlay_service),
) -> OverlayAccessResponse:
    _protect_capability_response(response)
    access = await service.get_or_create_channel(ctx.channel_id)
    return OverlayAccessResponse(**asdict(access))


@router.patch("/settings", response_model=OverlayAccessResponse)
async def update_overlay_access(
    body: OverlayAccessUpdate,
    response: Response,
    ctx: TenantContext = Depends(require_self_tenant_access),
    service: CommunityOverlayService = Depends(get_community_overlay_service),
) -> OverlayAccessResponse:
    _protect_capability_response(response)
    access = await service.set_enabled(ctx.channel_id, body.enabled)
    return OverlayAccessResponse(**asdict(access))


@router.post("/settings/rotate-key", response_model=OverlayAccessResponse)
async def rotate_overlay_key(
    response: Response,
    _action: Literal["community-overlay"] = Header(alias="X-Niibot-Action"),
    ctx: TenantContext = Depends(require_self_tenant_access),
    service: CommunityOverlayService = Depends(get_community_overlay_service),
) -> OverlayAccessResponse:
    _protect_capability_response(response)
    access = await service.rotate_public_key(ctx.channel_id)
    return OverlayAccessResponse(**asdict(access))


@router.get("/settings/theme", response_model=OverlayThemeStateResponse)
async def get_overlay_theme(
    ctx: TenantContext = Depends(require_self_tenant_access),
    service: CommunityOverlayService = Depends(get_community_overlay_service),
) -> OverlayThemeStateResponse:
    return _theme_state_response(await service.get_theme_state(ctx.channel_id))


@router.patch("/settings/theme/draft", response_model=OverlayThemeStateResponse)
async def update_overlay_theme_draft(
    body: OverlayThemeDraftUpdate,
    ctx: TenantContext = Depends(require_self_tenant_access),
    service: CommunityOverlayService = Depends(get_community_overlay_service),
) -> OverlayThemeStateResponse:
    state = await service.update_theme_draft(
        ctx.channel_id,
        body.theme.model_dump(),
        body.expected_draft_version,
    )
    return _theme_state_response(state)


@router.post("/settings/theme/publish", response_model=OverlayThemeStateResponse)
async def publish_overlay_theme(
    body: OverlayThemeActionRequest,
    _action: Literal["community-overlay"] = Header(alias="X-Niibot-Action"),
    ctx: TenantContext = Depends(require_self_tenant_access),
    service: CommunityOverlayService = Depends(get_community_overlay_service),
) -> OverlayThemeStateResponse:
    return _theme_state_response(
        await service.publish_theme(ctx.channel_id, body.expected_draft_version)
    )


@router.post("/settings/theme/reset-draft", response_model=OverlayThemeStateResponse)
async def reset_overlay_theme_draft(
    body: OverlayThemeActionRequest,
    _action: Literal["community-overlay"] = Header(alias="X-Niibot-Action"),
    ctx: TenantContext = Depends(require_self_tenant_access),
    service: CommunityOverlayService = Depends(get_community_overlay_service),
) -> OverlayThemeStateResponse:
    return _theme_state_response(
        await service.reset_theme_draft(ctx.channel_id, body.expected_draft_version)
    )
