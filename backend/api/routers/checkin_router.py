"""Authenticated, tenant-scoped daily check-in settings routes."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, Depends, File, Form, Header, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from core.dependencies import (
    get_attendance_service,
    get_db_pool,
    get_twitch_api,
    require_self_tenant_access,
    require_self_tenant_owner,
)
from core.rate_limit import RateLimiter
from services.checkin_import.formats import (
    CheckinImportValidationError,
    fetch_google_sheet_csv,
    parse_summary_bytes,
)
from services.checkin_import.models import (
    CheckinImportResult,
    ImportPreviewRow,
    ImportRowStatus,
)
from services.checkin_import.service import (
    CheckinImportService,
    PreviewNotFoundError,
    load_preview,
    stash_preview,
)
from services.tenant_service import TenantContext
from services.twitch_api import TwitchAPIClient
from shared.errors import InvalidInputError, NotFoundError, RateLimitedError
from shared.services.attendance import AttendanceService

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/checkin", tags=["checkin"])

_checkin_import_http = httpx.AsyncClient(timeout=10.0, follow_redirects=False)
_preview_rate_limiter = RateLimiter(max_calls=5, period=60.0)
_apply_rate_limiter = RateLimiter(max_calls=2, period=60.0)
_MAX_UPLOAD_READ = 5 * 1024 * 1024 + 1


async def close_checkin_import_http_client() -> None:
    await _checkin_import_http.aclose()


class CheckinSettingsInvalidError(InvalidInputError):
    code = "CHECKIN_SETTINGS.INVALID"
    user_message = "簽到設定內容無效，請檢查後再試"


class CheckinImportInvalidError(InvalidInputError):
    code = "CHECKIN_IMPORT.INVALID"
    user_message = "匯入內容無法辨識，請檢查格式與欄位"


class CheckinImportPreviewExpiredError(NotFoundError):
    code = "CHECKIN_IMPORT.PREVIEW_EXPIRED"
    user_message = "匯入預覽已過期，請重新讀取"


class CheckinImportRateLimitedError(RateLimitedError):
    code = "CHECKIN_IMPORT.RATE_LIMITED"
    user_message = "匯入操作太頻繁，請稍後再試"


class CheckinSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel_id: str
    timezone: str
    success_template: str
    duplicate_template: str
    reply_delay_seconds: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CheckinLeaderboardEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int
    user_id: str
    username: str
    display_name: str | None
    total_days: int
    last_checkin_date: date


class CheckinSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    success_template: str | None = Field(default=None, min_length=1, max_length=500)
    duplicate_template: str | None = Field(default=None, min_length=1, max_length=500)
    reply_delay_seconds: int | None = Field(default=None, ge=0, le=30)


class CheckinImportPreviewResponse(BaseModel):
    import_id: str
    source: str
    source_format: str
    source_timezone: str
    through_date: date
    sheet_name: str | None
    rows: list[ImportPreviewRow]
    default_selection: dict[str, bool]


class CheckinImportApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    import_id: str = Field(min_length=8, max_length=128)
    selected_keys: list[str] = Field(min_length=1, max_length=10_000)
    old_source_disabled: bool


class CheckinImportApplyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    batch_id: str
    imported_rows: int
    already_applied: bool


def get_checkin_import_service(
    pool=Depends(get_db_pool),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> CheckinImportService:
    return CheckinImportService(pool, twitch_api)


def _require_import_rate(limiter: RateLimiter, tenant: TenantContext) -> None:
    if not limiter.allow(f"{tenant.user_id}:{tenant.channel_id}"):
        raise CheckinImportRateLimitedError()


@router.get("/settings", response_model=CheckinSettingsResponse)
async def get_checkin_settings(
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: AttendanceService = Depends(get_attendance_service),
) -> CheckinSettingsResponse:
    settings = await service.get_settings(tenant.channel_id)
    return CheckinSettingsResponse.model_validate(settings)


@router.get("/leaderboard", response_model=list[CheckinLeaderboardEntryResponse])
async def get_checkin_leaderboard(
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: AttendanceService = Depends(get_attendance_service),
) -> list[CheckinLeaderboardEntryResponse]:
    entries = await service.get_leaderboard(tenant.channel_id)
    return [CheckinLeaderboardEntryResponse.model_validate(entry) for entry in entries]


@router.patch("/settings", response_model=CheckinSettingsResponse)
async def update_checkin_settings(
    body: CheckinSettingsUpdate,
    _action: Literal["checkin-settings"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: AttendanceService = Depends(get_attendance_service),
) -> CheckinSettingsResponse:
    if not body.model_fields_set or any(
        getattr(body, field_name) is None for field_name in body.model_fields_set
    ):
        raise CheckinSettingsInvalidError()

    try:
        settings = await service.update_settings(
            tenant.channel_id,
            timezone=body.timezone,
            success_template=body.success_template,
            duplicate_template=body.duplicate_template,
            reply_delay_seconds=body.reply_delay_seconds,
        )
    except ValueError:
        LOGGER.info("checkin_settings_validation_failed")
        raise CheckinSettingsInvalidError() from None

    LOGGER.info("checkin_settings_updated")
    return CheckinSettingsResponse.model_validate(settings)


@router.post("/import/summary/preview", response_model=CheckinImportPreviewResponse)
async def preview_checkin_import(
    source: str = Form(..., min_length=1, max_length=64),
    source_timezone: str = Form(..., min_length=1, max_length=64),
    through_date: date = Form(...),
    sheet_url: str | None = Form(default=None, max_length=2_048),
    sheet_name: str | None = Form(default=None, max_length=128),
    upload: UploadFile | None = File(default=None),
    _action: Literal["checkin-import"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_self_tenant_owner),
    service: CheckinImportService = Depends(get_checkin_import_service),
) -> CheckinImportPreviewResponse:
    """Build an owner-only, tenant-bound preview without persisting raw input."""
    _require_import_rate(_preview_rate_limiter, tenant)
    if (upload is None) == (not sheet_url):
        raise CheckinImportInvalidError()

    try:
        timezone = ZoneInfo(source_timezone)
    except ZoneInfoNotFoundError:
        raise CheckinImportInvalidError() from None

    try:
        if sheet_url:
            content = await fetch_google_sheet_csv(sheet_url, _checkin_import_http)
            parsed = parse_summary_bytes(
                "google-sheet.csv",
                content,
                through_date=through_date,
                source_format="google_sheets",
            )
        else:
            assert upload is not None
            if not upload.filename:
                raise CheckinImportValidationError("檔名不可為空")
            content = await upload.read(_MAX_UPLOAD_READ)
            parsed = parse_summary_bytes(
                upload.filename,
                content,
                through_date=through_date,
                sheet_name=sheet_name,
            )
        preview = await service.preview(
            channel_id=tenant.channel_id,
            source=source,
            source_timezone=source_timezone,
            through_date=through_date,
            parsed=parsed,
            today=datetime.now(timezone).date(),
        )
    except CheckinImportValidationError as exc:
        LOGGER.info("checkin_import_preview_invalid", extra={"reason": type(exc).__name__})
        raise CheckinImportInvalidError() from None
    except ValueError:
        raise CheckinImportInvalidError() from None
    finally:
        if upload is not None:
            await upload.close()

    import_id = stash_preview(tenant.user_id, tenant.channel_id, preview)
    LOGGER.info(
        "checkin_import_preview_ready",
        extra={
            "source": preview.source,
            "source_format": preview.source_format,
            "row_count": len(preview.rows),
        },
    )
    return CheckinImportPreviewResponse(
        import_id=import_id,
        source=preview.source,
        source_format=preview.source_format,
        source_timezone=preview.source_timezone,
        through_date=preview.through_date,
        sheet_name=preview.sheet_name,
        rows=list(preview.rows),
        default_selection={row.key: row.status is ImportRowStatus.READY for row in preview.rows},
    )


@router.post("/import/apply", response_model=CheckinImportApplyResponse)
async def apply_checkin_import(
    body: CheckinImportApplyRequest,
    _action: Literal["checkin-import"] = Header(alias="X-Niibot-Action"),
    tenant: TenantContext = Depends(require_self_tenant_owner),
    service: CheckinImportService = Depends(get_checkin_import_service),
) -> CheckinImportApplyResponse:
    """Atomically apply selected ready rows from a tenant-bound preview."""
    _require_import_rate(_apply_rate_limiter, tenant)
    try:
        preview = load_preview(tenant.user_id, tenant.channel_id, body.import_id)
    except PreviewNotFoundError:
        raise CheckinImportPreviewExpiredError() from None
    try:
        result: CheckinImportResult = await service.apply(
            channel_id=tenant.channel_id,
            actor_user_id=tenant.user_id,
            preview=preview,
            selected_keys=body.selected_keys,
            old_source_disabled=body.old_source_disabled,
        )
    except ValueError:
        raise CheckinImportInvalidError() from None
    LOGGER.info(
        "checkin_import_applied",
        extra={
            "source": preview.source,
            "imported_rows": result.imported_rows,
            "already_applied": result.already_applied,
        },
    )
    return CheckinImportApplyResponse.model_validate(result)
