"""Authenticated workspace discovery for Owner/MOD tenant routing."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.dependencies import get_active_session_payload, get_tenant_service
from services.tenant_service import TenantRole, TenantService, TenantSummary

router = APIRouter(prefix="/api/tenants", tags=["tenants"])

TenantCapability = Literal[
    "edit_operations",
    "switch_bot",
    "toggle_bot",
    "manage_bot_accounts",
    "manage_members",
    "manage_billing",
    "manage_security",
]

_MOD_CAPABILITIES: list[TenantCapability] = [
    "edit_operations",
    "switch_bot",
    "toggle_bot",
]
_OWNER_CAPABILITIES: list[TenantCapability] = [
    *_MOD_CAPABILITIES,
    "manage_bot_accounts",
    "manage_members",
    "manage_billing",
    "manage_security",
]


class TenantResponse(BaseModel):
    channel_id: str
    channel_name: str
    display_name: str | None
    enabled: bool
    role: TenantRole
    capabilities: list[TenantCapability]


class TenantListResponse(BaseModel):
    tenants: list[TenantResponse]


def _to_response(tenant: TenantSummary) -> TenantResponse:
    capabilities = _OWNER_CAPABILITIES if tenant.role == "owner" else _MOD_CAPABILITIES
    return TenantResponse(
        channel_id=tenant.channel_id,
        channel_name=tenant.channel_name,
        display_name=tenant.display_name,
        enabled=tenant.enabled,
        role=tenant.role,
        capabilities=list(capabilities),
    )


@router.get("", response_model=TenantListResponse)
async def list_tenants(
    payload: dict = Depends(get_active_session_payload),
    tenant_service: TenantService = Depends(get_tenant_service),
) -> TenantListResponse:
    """List only workspaces the authenticated identity can currently access."""
    tenants = await tenant_service.list_accessible_tenants(str(payload["sub"]))
    return TenantListResponse(tenants=[_to_response(tenant) for tenant in tenants])
