"""Public community event feed and tenant-owned overlay access settings."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from core.dependencies import (
    COMMUNITY_OVERLAY_NOTIFY_CHANNEL,
    get_community_overlay_service,
    get_notify_hub,
    require_self_tenant_access,
)
from core.error_handlers import log_request_failure
from core.rate_limit import RateLimiter
from services.notify_stream import NotifyWakeHub, StreamCapacityError, encode_sse
from services.tenant_service import TenantContext
from shared.community_overlay_blocks import get_community_overlay_block
from shared.errors import NotFoundError
from shared.models.attendance import (
    CommunityOverlaySnapshot,
    CommunityOverlayThemePublished,
    CommunityOverlayThemeState,
)
from shared.services.community_overlay import CommunityOverlayService

router = APIRouter(prefix="/api/live-display", tags=["live-display"])
_feed_limiter = RateLimiter(max_calls=240, period=60.0)
_public_theme_limiter = RateLimiter(max_calls=120, period=60.0)
_public_ip_limiter = RateLimiter(max_calls=600, period=60.0)
_preview_limiter = RateLimiter(max_calls=10, period=60.0)
_stream_limiter = RateLimiter(max_calls=30, period=60.0)
_STREAM_HEARTBEAT_SECONDS = 15.0
_STREAM_LEASE_SECONDS = 5 * 60.0


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


def _stream_payload(
    kind: Literal["snapshot", "update"], snapshot: CommunityOverlaySnapshot
) -> dict:
    return {
        "type": kind,
        "cursor": snapshot.cursor,
        "events": [
            OverlayEventResponse(**asdict(event)).model_dump(mode="json")
            for event in snapshot.events
        ],
        "themes": {
            block_type: _published_theme_response(theme).model_dump(mode="json")
            for block_type, theme in snapshot.themes.items()
        },
    }


class OverlayAccessResponse(BaseModel):
    public_key: UUID
    enabled: bool
    created_at: datetime
    updated_at: datetime


class OverlayAccessUpdate(BaseModel):
    enabled: bool


class OverlayPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    content_type: Literal["checkin", "tarot"]


class OverlayPreviewResponse(BaseModel):
    content_type: Literal["checkin", "tarot"]
    event_id: int


class OverlayThemeDraftUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    theme: dict[str, object]
    expected_draft_version: int = Field(strict=True, ge=1)


class OverlayThemeActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_draft_version: int = Field(strict=True, ge=1)


class OverlayThemePublishedResponse(BaseModel):
    revision_id: int | None
    renderer: str
    schema_version: int
    theme: dict[str, object]
    created_at: datetime | None


class OverlayThemeStateResponse(BaseModel):
    block_type: str
    renderer: str
    schema_version: int
    draft_version: int
    draft: dict[str, object]
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
        theme=dict(published.theme),
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
        block_type=state.block_type,
        renderer=state.renderer,
        schema_version=state.schema_version,
        draft_version=state.draft_version,
        draft=dict(state.draft_theme),
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
    block_type: str = Query(default="checkin"),
    service: CommunityOverlayService = Depends(get_community_overlay_service),
) -> OverlayThemePublishedResponse:
    """Return only the published renderer snapshot for a valid capability key."""
    public_key = _public_key_from_header(request, overlay_key)
    client_host = request.client.host if request.client else "unknown"
    selected_block = _require_theme_block(block_type)
    _public_theme_limiter.require(f"{client_host}:{public_key}:{selected_block}")
    published = await service.get_public_theme(public_key, selected_block)
    if published is None:
        raise CommunityOverlayNotFoundError()
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return _published_theme_response(published)


@router.get("/public/stream")
async def stream_public_overlay(
    request: Request,
    overlay_key: str = Header(alias="X-Overlay-Key"),
    after_id: int | None = Query(default=None, ge=0),
    service: CommunityOverlayService = Depends(get_community_overlay_service),
    hub: NotifyWakeHub = Depends(get_notify_hub),
) -> StreamingResponse:
    """Stream replay-safe Live Display snapshots over one long-lived request."""
    public_key = _public_key_from_header(request, overlay_key)
    client_host = request.client.host if request.client else "unknown"
    _stream_limiter.require(f"{client_host}:{public_key}")

    channel_id = await service.resolve_public_channel(public_key)
    if channel_id is None:
        raise CommunityOverlayNotFoundError()
    try:
        subscription = hub.subscribe(COMMUNITY_OVERLAY_NOTIFY_CHANNEL, channel_id)
    except StreamCapacityError:
        raise HTTPException(status_code=429, detail="Too many Live Display streams") from None
    try:
        snapshot = await service.get_stream_snapshot(public_key, after_id=after_id)
    except BaseException:
        subscription.close()
        raise
    if snapshot is None or snapshot.channel_id != channel_id:
        subscription.close()
        raise CommunityOverlayNotFoundError()

    async def frames() -> AsyncGenerator[str, None]:
        loop = asyncio.get_running_loop()
        lease_deadline = loop.time() + _STREAM_LEASE_SECONDS
        cursor = snapshot.cursor
        revisions = {block_type: theme.revision_id for block_type, theme in snapshot.themes.items()}
        needs_drain = len(snapshot.events) == 100
        try:
            yield encode_sse("snapshot", _stream_payload("snapshot", snapshot))
            while True:
                remaining_lease = lease_deadline - loop.time()
                if remaining_lease <= 0:
                    return
                if not needs_drain:
                    lease_expiry_wait = remaining_lease <= _STREAM_HEARTBEAT_SECONDS
                    try:
                        await asyncio.wait_for(
                            subscription.wait(),
                            timeout=min(_STREAM_HEARTBEAT_SECONDS, remaining_lease),
                        )
                    except TimeoutError:
                        if lease_expiry_wait:
                            return
                        if await service.resolve_public_channel(public_key) != channel_id:
                            return
                        yield encode_sse("heartbeat", {"at": datetime.now(UTC).isoformat()})
                        continue

                try:
                    current = await service.get_stream_snapshot(public_key, after_id=cursor)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log_request_failure(
                        request,
                        code="STREAM.ITERATION_FAILED",
                        status=500,
                        exc=exc,
                        context={"channel_id": channel_id, "event_class": "occasional"},
                    )
                    # Lets the client tell "we failed mid-stream" apart from the
                    # routine lease-expiry reconnect below — both otherwise look
                    # identical (a clean end of the response body).
                    yield encode_sse("stream_error", {"code": "STREAM.ITERATION_FAILED"})
                    return
                if current is None or current.channel_id != channel_id:
                    return
                needs_drain = len(current.events) == 100
                changed_themes = {
                    block_type: theme
                    for block_type, theme in current.themes.items()
                    if revisions.get(block_type) != theme.revision_id
                }
                if not current.events and not changed_themes:
                    cursor = current.cursor
                    continue
                cursor = current.cursor
                revisions.update(
                    {block_type: theme.revision_id for block_type, theme in changed_themes.items()}
                )
                update = CommunityOverlaySnapshot(
                    channel_id=current.channel_id,
                    cursor=current.cursor,
                    events=current.events,
                    themes=changed_themes,
                )
                yield encode_sse("update", _stream_payload("update", update))
        finally:
            subscription.close()

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store, no-transform",
            "Referrer-Policy": "no-referrer",
            "X-Accel-Buffering": "no",
        },
    )


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
    _action: Literal["live-display"] = Header(alias="X-Niibot-Action"),
    ctx: TenantContext = Depends(require_self_tenant_access),
    service: CommunityOverlayService = Depends(get_community_overlay_service),
) -> OverlayAccessResponse:
    _protect_capability_response(response)
    access = await service.rotate_public_key(ctx.channel_id)
    return OverlayAccessResponse(**asdict(access))


@router.post("/settings/preview", response_model=OverlayPreviewResponse)
async def publish_overlay_preview(
    body: OverlayPreviewRequest,
    response: Response,
    _action: Literal["live-display"] = Header(alias="X-Niibot-Action"),
    ctx: TenantContext = Depends(require_self_tenant_access),
    service: CommunityOverlayService = Depends(get_community_overlay_service),
) -> OverlayPreviewResponse:
    """Send a synthetic display event without executing its feature workflow."""
    _preview_limiter.require(f"{ctx.channel_id}:{ctx.user_id}")
    _protect_capability_response(response)
    event_id = await service.publish_preview(
        channel_id=ctx.channel_id,
        actor_user_id=ctx.user_id,
        content_type=body.content_type,
    )
    return OverlayPreviewResponse(content_type=body.content_type, event_id=event_id)


def _require_theme_block(block_type: str) -> str:
    try:
        get_community_overlay_block(block_type)
    except ValueError:
        raise CommunityOverlayNotFoundError() from None
    return block_type


def _validate_theme_input(block_type: str, theme: dict[str, object]) -> dict[str, object]:
    try:
        return get_community_overlay_block(block_type).validate_theme(theme)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/settings/blocks/{block_type}/theme", response_model=OverlayThemeStateResponse)
async def get_overlay_theme(
    block_type: str,
    ctx: TenantContext = Depends(require_self_tenant_access),
    service: CommunityOverlayService = Depends(get_community_overlay_service),
) -> OverlayThemeStateResponse:
    selected_block = _require_theme_block(block_type)
    return _theme_state_response(await service.get_theme_state(ctx.channel_id, selected_block))


@router.patch("/settings/blocks/{block_type}/theme/draft", response_model=OverlayThemeStateResponse)
async def update_overlay_theme_draft(
    block_type: str,
    body: OverlayThemeDraftUpdate,
    ctx: TenantContext = Depends(require_self_tenant_access),
    service: CommunityOverlayService = Depends(get_community_overlay_service),
) -> OverlayThemeStateResponse:
    selected_block = _require_theme_block(block_type)
    validated_theme = _validate_theme_input(selected_block, body.theme)
    state = await service.update_theme_draft(
        ctx.channel_id,
        selected_block,
        validated_theme,
        body.expected_draft_version,
    )
    return _theme_state_response(state)


@router.post(
    "/settings/blocks/{block_type}/theme/publish", response_model=OverlayThemeStateResponse
)
async def publish_overlay_theme(
    block_type: str,
    body: OverlayThemeActionRequest,
    _action: Literal["live-display"] = Header(alias="X-Niibot-Action"),
    ctx: TenantContext = Depends(require_self_tenant_access),
    service: CommunityOverlayService = Depends(get_community_overlay_service),
) -> OverlayThemeStateResponse:
    selected_block = _require_theme_block(block_type)
    return _theme_state_response(
        await service.publish_theme(ctx.channel_id, selected_block, body.expected_draft_version)
    )


@router.post(
    "/settings/blocks/{block_type}/theme/reset-draft",
    response_model=OverlayThemeStateResponse,
)
async def reset_overlay_theme_draft(
    block_type: str,
    body: OverlayThemeActionRequest,
    _action: Literal["live-display"] = Header(alias="X-Niibot-Action"),
    ctx: TenantContext = Depends(require_self_tenant_access),
    service: CommunityOverlayService = Depends(get_community_overlay_service),
) -> OverlayThemeStateResponse:
    selected_block = _require_theme_block(block_type)
    return _theme_state_response(
        await service.reset_theme_draft(ctx.channel_id, selected_block, body.expected_draft_version)
    )
