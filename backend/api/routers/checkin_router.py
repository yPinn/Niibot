"""Authenticated, tenant-scoped daily check-in settings routes."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field

from core.dependencies import get_attendance_service, require_self_tenant_access
from services.tenant_service import TenantContext
from shared.errors import InvalidInputError
from shared.services.attendance import AttendanceService

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/checkin", tags=["checkin"])


class CheckinSettingsInvalidError(InvalidInputError):
    code = "CHECKIN_SETTINGS.INVALID"
    user_message = "簽到設定內容無效，請檢查後再試"


class CheckinSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel_id: str
    timezone: str
    success_template: str
    duplicate_template: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CheckinSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    success_template: str | None = Field(default=None, min_length=1, max_length=500)
    duplicate_template: str | None = Field(default=None, min_length=1, max_length=500)


@router.get("/settings", response_model=CheckinSettingsResponse)
async def get_checkin_settings(
    tenant: TenantContext = Depends(require_self_tenant_access),
    service: AttendanceService = Depends(get_attendance_service),
) -> CheckinSettingsResponse:
    settings = await service.get_settings(tenant.channel_id)
    return CheckinSettingsResponse.model_validate(settings)


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
        )
    except ValueError:
        LOGGER.info("checkin_settings_validation_failed")
        raise CheckinSettingsInvalidError() from None

    LOGGER.info("checkin_settings_updated")
    return CheckinSettingsResponse.model_validate(settings)
