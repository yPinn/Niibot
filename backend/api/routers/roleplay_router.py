"""Tenant-path API for Canon Role-play authoring and activation."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from core.dependencies import get_roleplay_service, require_tenant_access
from core.rate_limit import RateLimiter
from services.roleplay_service import (
    RoleplayImportInvalidError,
    RoleplayImportOutcome,
    RoleplayImportTooLargeError,
    RoleplayService,
)
from services.tenant_service import TenantContext
from shared.models.roleplay import RoleplayRevision, RoleplaySet
from shared.roleplay import encode_roleplay_package
from shared.roleplay.portable import MAX_PORTABLE_ROLEPLAY_BYTES

router = APIRouter(prefix="/api/tenants/{channel_id}", tags=["roleplay"])

_read_limiter = RateLimiter(max_calls=120, period=60.0)
_mutation_limiter = RateLimiter(max_calls=30, period=60.0)
_publish_limiter = RateLimiter(max_calls=10, period=60.0)


class RoleplayRevisionSummaryResponse(BaseModel):
    id: int
    revision_number: int
    schema_version: int
    compiler_version: int
    content_digest: str
    published_at: datetime


class RoleplayRevisionResponse(RoleplayRevisionSummaryResponse):
    roleplay_set_id: UUID
    package: dict[str, object]
    capsule: str
    compact_capsule: str


class RoleplaySetSummaryResponse(BaseModel):
    id: UUID
    name: str
    draft_version: int
    published: RoleplayRevisionSummaryResponse | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RoleplaySetResponse(RoleplaySetSummaryResponse):
    draft: dict[str, object]


class RoleplaySetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    draft: dict[str, object]

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized


class RoleplayDraftUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_draft_version: int = Field(ge=1, strict=True)
    draft: dict[str, object]
    name: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def normalize_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized


class RoleplayPublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_draft_version: int = Field(ge=1, strict=True)


class RoleplayActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision_id: int = Field(ge=1, strict=True)


class RoleplayImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["use", "copy"]
    character: dict[str, object]


class AssistantModeResponse(BaseModel):
    assistant_mode: Literal["persona", "roleplay"]
    active_roleplay_revision_id: int | None


class RoleplayImportResponse(BaseModel):
    mode: Literal["use", "copy"]
    reused: bool
    roleplay_set: RoleplaySetResponse
    active_roleplay_revision_id: int | None


def _revision_summary(revision: RoleplayRevision) -> RoleplayRevisionSummaryResponse:
    return RoleplayRevisionSummaryResponse(
        id=revision.id,
        revision_number=revision.revision_number,
        schema_version=revision.compiled.schema_version,
        compiler_version=revision.compiled.compiler_version,
        content_digest=revision.compiled.content_digest,
        published_at=revision.published_at,
    )


def _revision_response(revision: RoleplayRevision) -> RoleplayRevisionResponse:
    return RoleplayRevisionResponse(
        **_revision_summary(revision).model_dump(),
        roleplay_set_id=revision.roleplay_set_id,
        package=encode_roleplay_package(revision.package),
        capsule=revision.compiled.capsule,
        compact_capsule=revision.compiled.compact_capsule,
    )


def _set_summary(roleplay_set: RoleplaySet) -> RoleplaySetSummaryResponse:
    published = (
        _revision_summary(roleplay_set.published) if roleplay_set.published is not None else None
    )
    return RoleplaySetSummaryResponse(
        id=roleplay_set.id,
        name=roleplay_set.name,
        draft_version=roleplay_set.draft_version,
        published=published,
        archived_at=roleplay_set.archived_at,
        created_at=roleplay_set.created_at,
        updated_at=roleplay_set.updated_at,
    )


def _set_response(roleplay_set: RoleplaySet) -> RoleplaySetResponse:
    return RoleplaySetResponse(
        **_set_summary(roleplay_set).model_dump(),
        draft=encode_roleplay_package(roleplay_set.draft),
    )


def _rate_key(request: Request, tenant: TenantContext) -> str:
    client_ip = request.client.host if request.client else "unknown"
    return f"{tenant.user_id}:{tenant.channel_id}:{client_ip}"


def _import_response(outcome: RoleplayImportOutcome) -> RoleplayImportResponse:
    return RoleplayImportResponse(
        mode=outcome.mode,
        reused=outcome.reused,
        roleplay_set=_set_response(outcome.roleplay_set),
        active_roleplay_revision_id=(outcome.revision.id if outcome.revision is not None else None),
    )


async def _read_import_request(request: Request) -> RoleplayImportRequest:
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit():
        if int(content_length) > MAX_PORTABLE_ROLEPLAY_BYTES:
            raise RoleplayImportTooLargeError()
    raw = await request.body()
    if len(raw) > MAX_PORTABLE_ROLEPLAY_BYTES:
        raise RoleplayImportTooLargeError()
    try:
        return RoleplayImportRequest.model_validate_json(raw)
    except ValidationError:
        raise RoleplayImportInvalidError() from None


def _download_disposition(name: str) -> str:
    safe_name = re.sub(r"[\x00-\x1f\x7f/\\]+", "-", name).strip(" .-")[:60]
    encoded = quote(f"{safe_name or 'roleplay-character'}.niibot-roleplay.json", safe="")
    return f"attachment; filename=\"niibot-roleplay.json\"; filename*=UTF-8''{encoded}"


@router.get("/roleplay-sets", response_model=list[RoleplaySetSummaryResponse])
async def list_roleplay_sets(
    request: Request,
    include_archived: bool = Query(default=False),
    tenant: TenantContext = Depends(require_tenant_access),
    service: RoleplayService = Depends(get_roleplay_service),
) -> list[RoleplaySetSummaryResponse]:
    _read_limiter.require(_rate_key(request, tenant))
    roleplay_sets = await service.list_sets(
        tenant.channel_id,
        include_archived=include_archived,
    )
    return [_set_summary(roleplay_set) for roleplay_set in roleplay_sets]


@router.post(
    "/roleplay-sets",
    response_model=RoleplaySetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_roleplay_set(
    body: RoleplaySetCreate,
    request: Request,
    _action: Literal["roleplay-settings"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_tenant_access),
    service: RoleplayService = Depends(get_roleplay_service),
) -> RoleplaySetResponse:
    _mutation_limiter.require(_rate_key(request, tenant))
    roleplay_set = await service.create_set(
        tenant.channel_id,
        name=body.name,
        draft=body.draft,
    )
    return _set_response(roleplay_set)


@router.get("/roleplay-sets/{roleplay_set_id}", response_model=RoleplaySetResponse)
async def get_roleplay_set(
    roleplay_set_id: UUID,
    request: Request,
    tenant: TenantContext = Depends(require_tenant_access),
    service: RoleplayService = Depends(get_roleplay_service),
) -> RoleplaySetResponse:
    _read_limiter.require(_rate_key(request, tenant))
    roleplay_set = await service.get_set(tenant.channel_id, roleplay_set_id)
    return _set_response(roleplay_set)


@router.get("/roleplay-sets/{roleplay_set_id}/revisions/{revision_id}/export")
async def export_roleplay_revision(
    roleplay_set_id: UUID,
    revision_id: int,
    request: Request,
    tenant: TenantContext = Depends(require_tenant_access),
    service: RoleplayService = Depends(get_roleplay_service),
) -> JSONResponse:
    _read_limiter.require(_rate_key(request, tenant))
    document = await service.export_revision(
        tenant.channel_id,
        roleplay_set_id,
        revision_id,
    )
    manifest = document.get("manifest")
    name = manifest.get("name") if isinstance(manifest, dict) else "roleplay-character"
    return JSONResponse(
        content=document,
        media_type="application/vnd.niibot.roleplay-character+json",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": _download_disposition(str(name)),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/roleplay-imports", response_model=RoleplayImportResponse)
async def import_roleplay_character(
    request: Request,
    _action: Literal["roleplay-settings"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_tenant_access),
    service: RoleplayService = Depends(get_roleplay_service),
) -> RoleplayImportResponse:
    key = _rate_key(request, tenant)
    _mutation_limiter.require(key)
    _publish_limiter.require(key)
    body = await _read_import_request(request)
    outcome = await service.import_character(
        tenant.channel_id,
        mode=body.mode,
        character=body.character,
    )
    return _import_response(outcome)


@router.patch("/roleplay-sets/{roleplay_set_id}", response_model=RoleplaySetResponse)
async def update_roleplay_draft(
    roleplay_set_id: UUID,
    body: RoleplayDraftUpdate,
    request: Request,
    _action: Literal["roleplay-settings"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_tenant_access),
    service: RoleplayService = Depends(get_roleplay_service),
) -> RoleplaySetResponse:
    _mutation_limiter.require(_rate_key(request, tenant))
    roleplay_set = await service.update_draft(
        tenant.channel_id,
        roleplay_set_id,
        name=body.name,
        draft=body.draft,
        expected_draft_version=body.expected_draft_version,
    )
    return _set_response(roleplay_set)


@router.post(
    "/roleplay-sets/{roleplay_set_id}/revisions",
    response_model=RoleplayRevisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def publish_roleplay_revision(
    roleplay_set_id: UUID,
    body: RoleplayPublishRequest,
    request: Request,
    _action: Literal["roleplay-settings"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_tenant_access),
    service: RoleplayService = Depends(get_roleplay_service),
) -> RoleplayRevisionResponse:
    key = _rate_key(request, tenant)
    _mutation_limiter.require(key)
    _publish_limiter.require(key)
    revision = await service.publish(
        tenant.channel_id,
        roleplay_set_id,
        expected_draft_version=body.expected_draft_version,
    )
    return _revision_response(revision)


@router.put(
    "/roleplay-sets/{roleplay_set_id}/active-revision",
    response_model=AssistantModeResponse,
)
async def activate_roleplay_revision(
    roleplay_set_id: UUID,
    body: RoleplayActivateRequest,
    request: Request,
    _action: Literal["roleplay-settings"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_tenant_access),
    service: RoleplayService = Depends(get_roleplay_service),
) -> AssistantModeResponse:
    _mutation_limiter.require(_rate_key(request, tenant))
    revision = await service.activate(
        tenant.channel_id,
        roleplay_set_id,
        revision_id=body.revision_id,
    )
    return AssistantModeResponse(
        assistant_mode="roleplay",
        active_roleplay_revision_id=revision.id,
    )


@router.delete("/active-roleplay", response_model=AssistantModeResponse)
async def use_persona_mode(
    request: Request,
    _action: Literal["roleplay-settings"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_tenant_access),
    service: RoleplayService = Depends(get_roleplay_service),
) -> AssistantModeResponse:
    _mutation_limiter.require(_rate_key(request, tenant))
    await service.use_persona(tenant.channel_id)
    return AssistantModeResponse(
        assistant_mode="persona",
        active_roleplay_revision_id=None,
    )


@router.delete("/roleplay-sets/{roleplay_set_id}", response_model=RoleplaySetResponse)
async def archive_roleplay_set(
    roleplay_set_id: UUID,
    request: Request,
    _action: Literal["roleplay-settings"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_tenant_access),
    service: RoleplayService = Depends(get_roleplay_service),
) -> RoleplaySetResponse:
    _mutation_limiter.require(_rate_key(request, tenant))
    roleplay_set = await service.archive(tenant.channel_id, roleplay_set_id)
    return _set_response(roleplay_set)
