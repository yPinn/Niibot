"""Tenant-scoped timed VIP settings API contracts."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-auth-router-tests")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.dependencies import (
    get_channel_service,
    get_twitch_api,
    get_vip_service,
    require_self_tenant_access,
)
from core.error_handlers import register_exception_handlers
from routers.vip_router import router as _vip_router
from services.tenant_service import TenantContext
from shared.models.vip import VipChannelSettings

CHANNEL_ID = "channel-123"
_ACTION = {"X-Niibot-Action": "vip-management"}
_NOW = datetime(2026, 8, 31, tzinfo=UTC)


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


def _service() -> MagicMock:
    service = MagicMock()
    service.get_state = AsyncMock(
        return_value=MagicMock(
            settings=VipChannelSettings(
                channel_id=CHANNEL_ID,
                slot_limit=25,
                tracking_started_at=_NOW,
                last_full_sync_at=_NOW,
            ),
            rules=(),
            entitlements=(),
            redemptions=(),
        )
    )
    service.update_slot_limit = AsyncMock(
        return_value=VipChannelSettings(
            channel_id=CHANNEL_ID,
            slot_limit=30,
            tracking_started_at=_NOW,
            last_full_sync_at=_NOW,
        )
    )
    service.initialize = AsyncMock(
        return_value=VipChannelSettings(
            channel_id=CHANNEL_ID,
            slot_limit=30,
            tracking_started_at=_NOW,
            last_full_sync_at=_NOW,
        )
    )
    service.upsert_rule = AsyncMock()
    service.set_rules_enabled = AsyncMock(return_value=())
    service.adopt_external_redemption = AsyncMock(return_value=MagicMock())
    service.keep_external_redemption = AsyncMock()
    return service


def _client(
    service: MagicMock,
    *,
    twitch: MagicMock | None = None,
    channels: MagicMock | None = None,
) -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(_vip_router)
    app.dependency_overrides[require_self_tenant_access] = lambda: TenantContext(
        channel_id=CHANNEL_ID,
        user_id="user-1",
        role="owner",
    )
    app.dependency_overrides[get_vip_service] = lambda: service
    app.dependency_overrides[get_twitch_api] = lambda: twitch or MagicMock()
    app.dependency_overrides[get_channel_service] = lambda: channels or MagicMock()
    return TestClient(app, raise_server_exceptions=False)


def test_get_state_uses_authenticated_tenant() -> None:
    service = _service()

    response = _client(service).get("/api/vip/state")

    assert response.status_code == 200
    assert response.json()["settings"]["channel_id"] == CHANNEL_ID
    service.get_state.assert_awaited_once_with(CHANNEL_ID)


def test_patch_slot_limit_rejects_tenant_id_and_requires_action_header() -> None:
    service = _service()
    client = _client(service)

    injected = client.patch(
        "/api/vip/settings",
        json={"channel_id": "other", "slot_limit": 30},
        headers=_ACTION,
    )
    missing_header = client.patch("/api/vip/settings", json={"slot_limit": 30})

    assert injected.status_code == 422
    assert missing_header.status_code == 422
    service.update_slot_limit.assert_not_awaited()


def test_initialize_requires_complete_twitch_snapshot_before_writing() -> None:
    service = _service()
    twitch = MagicMock()
    twitch.get_vips = AsyncMock(
        return_value=[
            {"user_id": "u1", "user_login": "alice", "user_name": "Alice"},
            {"user_id": "u2", "user_login": "bob", "user_name": "Bob"},
        ]
    )
    channels = MagicMock()
    channels.get_token_with_refresh = AsyncMock(return_value="token")

    response = _client(service, twitch=twitch, channels=channels).post(
        "/api/vip/initialize", json={"slot_limit": 30}, headers=_ACTION
    )

    assert response.status_code == 200
    twitch.get_vips.assert_awaited_once_with(CHANNEL_ID, "token")
    call = service.initialize.await_args.kwargs
    assert call["channel_id"] == CHANNEL_ID
    assert call["slot_limit"] == 30
    assert [member.user_id for member in call["members"]] == ["u1", "u2"]


def test_initialize_does_not_write_when_twitch_snapshot_fails() -> None:
    service = _service()
    twitch = MagicMock()
    twitch.get_vips = AsyncMock(side_effect=RuntimeError("upstream details"))
    channels = MagicMock()
    channels.get_token_with_refresh = AsyncMock(return_value="token")

    response = _client(service, twitch=twitch, channels=channels).post(
        "/api/vip/initialize", json={"slot_limit": 30}, headers=_ACTION
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "VIP.TWITCH_UNAVAILABLE"
    assert "upstream details" not in response.text
    service.initialize.assert_not_awaited()


def test_rule_binding_must_match_a_real_twitch_reward() -> None:
    service = _service()
    twitch = MagicMock()
    twitch.get_custom_rewards = AsyncMock(return_value=[])
    channels = MagicMock()
    channels.get_token_with_refresh = AsyncMock(return_value="token")

    response = _client(service, twitch=twitch, channels=channels).put(
        "/api/vip/rules/reward-missing",
        json={"duration_months": 3, "is_permanent": False, "enabled": True},
        headers=_ACTION,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "VIP.REWARD_NOT_FOUND"
    service.upsert_rule.assert_not_awaited()


def test_keep_external_review_is_tenant_scoped_and_requires_action_header() -> None:
    service = _service()
    client = _client(service)

    missing = client.post("/api/vip/reviews/redemption-1/keep-external")
    response = client.post("/api/vip/reviews/redemption-1/keep-external", headers=_ACTION)

    assert missing.status_code == 422
    assert response.status_code == 204
    service.keep_external_redemption.assert_awaited_once_with(
        channel_id=CHANNEL_ID, redemption_id="redemption-1"
    )


def test_toggle_all_rules_uses_static_route_and_authenticated_tenant() -> None:
    service = _service()

    response = _client(service).patch(
        "/api/vip/rules/enabled", json={"enabled": False}, headers=_ACTION
    )

    assert response.status_code == 200
    assert response.json() == []
    service.set_rules_enabled.assert_awaited_once_with(channel_id=CHANNEL_ID, enabled=False)
