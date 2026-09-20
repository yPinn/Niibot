"""Admission enforcement for all channel- and tenant-scoped dependencies."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-auth-router-tests")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from core.dependencies import (
    get_active_session_payload,
    get_admission_service,
    get_current_channel_id,
    get_tenant_service,
    require_self_tenant_access,
    require_tenant_access,
    require_tenant_owner,
)
from services import TenantContext


def _make_client(*, active: bool) -> tuple[TestClient, MagicMock]:
    admission = MagicMock()
    admission.is_active = AsyncMock(return_value=active)
    tenant = MagicMock()
    tenant.assert_access = AsyncMock(
        return_value=TenantContext(channel_id="channel-1", user_id="user-1", role="owner")
    )

    app = FastAPI()

    @app.get("/legacy")
    async def legacy(channel_id: str = Depends(get_current_channel_id)):
        return {"channel_id": channel_id}

    @app.get("/self-tenant")
    async def self_tenant(ctx: TenantContext = Depends(require_self_tenant_access)):
        return {"channel_id": ctx.channel_id}

    @app.get("/tenant/{channel_id}")
    async def tenant_path(ctx: TenantContext = Depends(require_tenant_access)):
        return {"channel_id": ctx.channel_id}

    @app.get("/tenant-owner/{channel_id}")
    async def tenant_owner(ctx: TenantContext = Depends(require_tenant_owner)):
        return {"channel_id": ctx.channel_id}

    app.dependency_overrides[get_active_session_payload] = lambda: {
        "sub": "user-1",
        "platform_user_id": "channel-1",
    }
    app.dependency_overrides[get_admission_service] = lambda: admission
    app.dependency_overrides[get_tenant_service] = lambda: tenant
    return TestClient(app, raise_server_exceptions=False), tenant


def test_active_membership_can_use_all_channel_dependencies():
    client, tenant = _make_client(active=True)

    assert client.get("/legacy").status_code == 200
    assert client.get("/self-tenant").status_code == 200
    assert client.get("/tenant/channel-1").status_code == 200
    assert client.get("/tenant-owner/channel-1").status_code == 200
    assert tenant.assert_access.await_count == 3
    assert tenant.assert_access.await_args_list[-1].kwargs["required_role"] == "owner"


def test_inactive_broadcaster_membership_does_not_block_explicit_collaborator_tenant():
    client, tenant = _make_client(active=False)

    assert client.get("/legacy").status_code == 403
    assert client.get("/self-tenant").status_code == 403
    assert client.get("/tenant/channel-1").status_code == 200
    assert client.get("/tenant-owner/channel-1").status_code == 200
    assert tenant.assert_access.await_count == 2
