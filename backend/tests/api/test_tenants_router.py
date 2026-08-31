"""Tenant workspace discovery API contracts."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-auth-router-tests")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.dependencies import get_tenant_service, get_token_payload
from core.error_handlers import register_exception_handlers
from routers.tenants_router import router
from services.tenant_service import TenantSummary


def _client(tenants: list[TenantSummary]) -> tuple[TestClient, MagicMock]:
    service = MagicMock()
    service.list_accessible_tenants = AsyncMock(return_value=tenants)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_token_payload] = lambda: {
        "sub": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "platform_user_id": "12345",
    }
    app.dependency_overrides[get_tenant_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False), service


def test_lists_only_server_resolved_workspaces_with_role_capabilities():
    client, service = _client(
        [
            TenantSummary(
                channel_id="12345",
                channel_name="alice",
                display_name="Alice",
                enabled=True,
                role="manager",
            )
        ]
    )

    response = client.get("/api/tenants")

    assert response.status_code == 200
    assert response.json() == {
        "tenants": [
            {
                "channel_id": "12345",
                "channel_name": "alice",
                "display_name": "Alice",
                "enabled": True,
                "role": "manager",
                "capabilities": ["edit_operations", "switch_bot", "toggle_bot"],
            }
        ]
    }
    service.list_accessible_tenants.assert_awaited_once_with("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def test_owner_receives_owner_only_capabilities():
    client, _ = _client(
        [
            TenantSummary(
                channel_id="12345",
                channel_name="alice",
                display_name=None,
                enabled=False,
                role="owner",
            )
        ]
    )

    capabilities = client.get("/api/tenants").json()["tenants"][0]["capabilities"]

    assert "manage_bot_accounts" in capabilities
    assert "manage_members" in capabilities
    assert "manage_billing" in capabilities
    assert "manage_security" in capabilities
