"""Tests for public community overlay feed and private key management."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-overlay-tests")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.community_overlay_router as community_overlay_router
from core.dependencies import get_community_overlay_service, require_self_tenant_access
from core.error_handlers import register_exception_handlers
from core.rate_limit import RateLimiter
from routers.community_overlay_router import router
from shared.community_overlay_themes import DEFAULT_OVERLAY_THEME
from shared.models.attendance import (
    CommunityOverlayAccess,
    CommunityOverlayEvent,
    CommunityOverlayFeed,
    CommunityOverlayThemePublished,
    CommunityOverlayThemeState,
)

_KEY = UUID("11111111-1111-4111-8111-111111111111")
_NOW = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)
_PUBLIC_HEADERS = {"X-Overlay-Key": str(_KEY)}
_ACTION_HEADERS = {"X-Niibot-Action": "live-display"}


def test_router_uses_only_the_live_display_api_prefix() -> None:
    assert router.prefix == "/api/live-display"
    paths = {route.path for route in router.routes}
    assert all(path.startswith("/api/live-display/") for path in paths)
    assert not any(path.startswith("/api/community-overlay/") for path in paths)
    assert _client(_service()).get("/api/community-overlay/settings").status_code == 404


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


def _event() -> CommunityOverlayEvent:
    return CommunityOverlayEvent(
        id=13,
        channel_id="ch1",
        event_type="checkin.recorded",
        schema_version=1,
        source="twitch",
        actor_user_id="u1",
        actor_display_name="Alice",
        payload={"total_days": 3, "checkin_date": "2026-08-30"},
        occurred_at=_NOW,
        expires_at=_NOW + timedelta(minutes=10),
    )


def _access() -> CommunityOverlayAccess:
    return CommunityOverlayAccess(
        channel_id="ch1",
        public_key=_KEY,
        enabled=True,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _published_theme() -> CommunityOverlayThemePublished:
    return CommunityOverlayThemePublished(
        revision_id=41,
        renderer="checkin-card",
        schema_version=1,
        theme=DEFAULT_OVERLAY_THEME,
        created_at=_NOW,
    )


def _theme_state(*, draft: dict[str, object] | None = None) -> CommunityOverlayThemeState:
    return CommunityOverlayThemeState(
        channel_id="ch1",
        block_type="checkin",
        renderer="checkin-card",
        schema_version=1,
        draft_theme=draft or DEFAULT_OVERLAY_THEME,
        published=_published_theme(),
        updated_at=_NOW,
    )


def _client(service: MagicMock) -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_community_overlay_service] = lambda: service
    app.dependency_overrides[require_self_tenant_access] = lambda: SimpleNamespace(
        channel_id="ch1", user_id="owner1"
    )
    return TestClient(app, raise_server_exceptions=False)


def _service() -> MagicMock:
    service = MagicMock()
    service.get_feed = AsyncMock(return_value=CommunityOverlayFeed(cursor=13, events=(_event(),)))
    service.get_or_create_channel = AsyncMock(return_value=_access())
    service.rotate_public_key = AsyncMock(return_value=_access())
    service.set_enabled = AsyncMock(return_value=_access())
    service.get_theme_state = AsyncMock(return_value=_theme_state())
    service.update_theme_draft = AsyncMock(return_value=_theme_state())
    service.publish_theme = AsyncMock(return_value=_theme_state())
    service.reset_theme_draft = AsyncMock(return_value=_theme_state())
    service.get_public_theme = AsyncMock(return_value=_published_theme())
    service.publish_preview = AsyncMock(return_value=91)
    return service


class TestPublicFeed:
    def test_returns_cursor_events_and_validates_limit(self):
        service = _service()
        client = _client(service)

        response = client.get(
            "/api/live-display/public/events?after_id=12&limit=25",
            headers=_PUBLIC_HEADERS,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["cursor"] == 13
        assert body["events"][0]["event_type"] == "checkin.recorded"
        assert "actor_user_id" not in body["events"][0]
        assert service.get_feed.await_args.kwargs["after_id"] == 12
        assert service.get_feed.await_args.kwargs["limit"] == 25
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"

    @pytest.mark.parametrize("limit", [0, 101])
    def test_rejects_invalid_limit(self, limit: int):
        client = _client(_service())

        response = client.get(
            f"/api/live-display/public/events?limit={limit}", headers=_PUBLIC_HEADERS
        )

        assert response.status_code == 422

    def test_unknown_key_returns_not_found_without_tenant_details(self):
        service = _service()
        service.get_feed = AsyncMock(return_value=None)
        client = _client(service)

        response = client.get("/api/live-display/public/events", headers=_PUBLIC_HEADERS)

        assert response.status_code == 404
        assert "ch1" not in response.text

    def test_ip_limit_cannot_be_bypassed_with_rotating_or_invalid_keys(self, monkeypatch):
        monkeypatch.setattr(
            community_overlay_router,
            "_public_ip_limiter",
            RateLimiter(max_calls=2, period=60.0),
        )
        client = _client(_service())

        invalid = client.get(
            "/api/live-display/public/events", headers={"X-Overlay-Key": "invalid"}
        )
        first_valid = client.get("/api/live-display/public/events", headers=_PUBLIC_HEADERS)
        rotated = client.get(
            "/api/live-display/public/events",
            headers={"X-Overlay-Key": "22222222-2222-4222-8222-222222222222"},
        )

        assert invalid.status_code == 404
        assert first_valid.status_code == 200
        assert rotated.status_code == 429


class TestPublicTheme:
    def test_returns_published_snapshot_with_capability_headers(self):
        service = _service()
        client = _client(service)

        response = client.get("/api/live-display/public/theme", headers=_PUBLIC_HEADERS)

        assert response.status_code == 200
        assert response.json() == {
            "revision_id": 41,
            "renderer": "checkin-card",
            "schema_version": 1,
            "theme": DEFAULT_OVERLAY_THEME,
            "created_at": _NOW.isoformat().replace("+00:00", "Z"),
        }
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        service.get_public_theme.assert_awaited_once_with(_KEY, "checkin")

    def test_rejects_unknown_block_before_public_lookup(self):
        service = _service()
        client = _client(service)

        response = client.get(
            "/api/live-display/public/theme?block_type=fortune",
            headers=_PUBLIC_HEADERS,
        )

        assert response.status_code == 404
        service.get_public_theme.assert_not_awaited()

    def test_unknown_or_disabled_key_does_not_expose_tenant(self):
        service = _service()
        service.get_public_theme = AsyncMock(return_value=None)
        client = _client(service)

        response = client.get("/api/live-display/public/theme", headers=_PUBLIC_HEADERS)

        assert response.status_code == 404
        assert "ch1" not in response.text


class TestOverlayAccessManagement:
    def test_get_settings_uses_authenticated_tenant(self):
        service = _service()
        client = _client(service)

        response = client.get("/api/live-display/settings")

        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-store"
        service.get_or_create_channel.assert_awaited_once_with("ch1")

    def test_rotate_key_uses_authenticated_tenant(self):
        service = _service()
        client = _client(service)

        response = client.post("/api/live-display/settings/rotate-key", headers=_ACTION_HEADERS)

        assert response.status_code == 200
        service.rotate_public_key.assert_awaited_once_with("ch1")

    def test_rotate_key_rejects_form_style_post_without_action_header(self):
        service = _service()
        client = _client(service)

        response = client.post("/api/live-display/settings/rotate-key")

        assert response.status_code == 422
        service.rotate_public_key.assert_not_awaited()

    def test_update_enabled_uses_authenticated_tenant(self):
        service = _service()
        client = _client(service)

        response = client.patch("/api/live-display/settings", json={"enabled": False})

        assert response.status_code == 200
        service.set_enabled.assert_awaited_once_with("ch1", False)


class TestOverlayPreview:
    def test_publishes_a_tenant_scoped_checkin_preview(self):
        service = _service()
        client = _client(service)

        response = client.post(
            "/api/live-display/settings/preview",
            headers=_ACTION_HEADERS,
            json={"content_type": "checkin"},
        )

        assert response.status_code == 200
        assert response.json() == {"content_type": "checkin", "event_id": 91}
        service.publish_preview.assert_awaited_once_with(
            channel_id="ch1", actor_user_id="owner1", content_type="checkin"
        )

    def test_rejects_unknown_content_type_before_service_call(self):
        service = _service()
        client = _client(service)

        response = client.post(
            "/api/live-display/settings/preview",
            headers=_ACTION_HEADERS,
            json={"content_type": "fortune"},
        )

        assert response.status_code == 422
        service.publish_preview.assert_not_awaited()

    def test_publishes_a_tenant_scoped_tarot_preview(self):
        service = _service()
        client = _client(service)

        response = client.post(
            "/api/live-display/settings/preview",
            headers=_ACTION_HEADERS,
            json={"content_type": "tarot"},
        )

        assert response.status_code == 200
        assert response.json() == {"content_type": "tarot", "event_id": 91}
        service.publish_preview.assert_awaited_once_with(
            channel_id="ch1", actor_user_id="owner1", content_type="tarot"
        )

    def test_requires_action_header(self):
        service = _service()
        client = _client(service)

        response = client.post(
            "/api/live-display/settings/preview", json={"content_type": "checkin"}
        )

        assert response.status_code == 422
        service.publish_preview.assert_not_awaited()

    def test_limits_repeated_preview_events_per_tenant_user(self, monkeypatch):
        monkeypatch.setattr(
            community_overlay_router,
            "_preview_limiter",
            RateLimiter(max_calls=1, period=60.0),
        )
        service = _service()
        client = _client(service)

        first = client.post(
            "/api/live-display/settings/preview",
            headers=_ACTION_HEADERS,
            json={"content_type": "checkin"},
        )
        second = client.post(
            "/api/live-display/settings/preview",
            headers=_ACTION_HEADERS,
            json={"content_type": "checkin"},
        )

        assert first.status_code == 200
        assert second.status_code == 429
        service.publish_preview.assert_awaited_once()


class TestOverlayThemeManagement:
    def test_get_theme_uses_authenticated_tenant(self):
        service = _service()
        client = _client(service)

        response = client.get("/api/live-display/settings/blocks/checkin/theme")

        assert response.status_code == 200
        assert response.json()["block_type"] == "checkin"
        assert response.json()["has_unpublished_changes"] is False
        service.get_theme_state.assert_awaited_once_with("ch1", "checkin")

    def test_update_draft_uses_authenticated_tenant_and_complete_theme(self):
        service = _service()
        theme = {**DEFAULT_OVERLAY_THEME, "placement": "top-left"}
        service.update_theme_draft = AsyncMock(return_value=_theme_state(draft=theme))
        client = _client(service)

        response = client.patch(
            "/api/live-display/settings/blocks/checkin/theme/draft",
            json={"theme": theme, "expected_draft_version": 1},
        )

        assert response.status_code == 200
        service.update_theme_draft.assert_awaited_once_with("ch1", "checkin", theme, 1)

    def test_update_draft_accepts_low_contrast_as_a_stylistic_choice(self):
        """Contrast is advisory-only client-side; the API must never reject on it."""
        service = _service()
        theme = {**DEFAULT_OVERLAY_THEME, "surface_color": "#241B34"}
        service.update_theme_draft = AsyncMock(return_value=_theme_state(draft=theme))
        client = _client(service)

        response = client.patch(
            "/api/live-display/settings/blocks/checkin/theme/draft",
            json={"theme": theme, "expected_draft_version": 1},
        )

        assert response.status_code == 200
        service.update_theme_draft.assert_awaited_once_with("ch1", "checkin", theme, 1)

    @pytest.mark.parametrize(
        "theme",
        [
            {**DEFAULT_OVERLAY_THEME, "custom_css": "* { display: none }"},
            {**DEFAULT_OVERLAY_THEME, "radius_px": 99},
            {**DEFAULT_OVERLAY_THEME, "radius_px": True},
            {**DEFAULT_OVERLAY_THEME, "display_ms": "5500"},
            {**DEFAULT_OVERLAY_THEME, "surface_color": "red"},
            {**DEFAULT_OVERLAY_THEME, "placement": "center"},
        ],
    )
    def test_update_draft_rejects_unsupported_or_invalid_input(self, theme: dict):
        service = _service()
        client = _client(service)

        response = client.patch(
            "/api/live-display/settings/blocks/checkin/theme/draft",
            json={"theme": theme, "expected_draft_version": 1},
        )

        assert response.status_code == 422
        service.update_theme_draft.assert_not_awaited()

    @pytest.mark.parametrize(
        ("path", "method_name"),
        [
            ("publish", "publish_theme"),
            ("reset-draft", "reset_theme_draft"),
        ],
    )
    def test_theme_actions_use_authenticated_tenant(self, path: str, method_name: str):
        service = _service()
        client = _client(service)

        response = client.post(
            f"/api/live-display/settings/blocks/checkin/theme/{path}",
            headers=_ACTION_HEADERS,
            json={"expected_draft_version": 1},
        )

        assert response.status_code == 200
        getattr(service, method_name).assert_awaited_once_with("ch1", "checkin", 1)

    def test_rejects_unregistered_theme_block(self):
        service = _service()
        client = _client(service)

        response = client.get("/api/live-display/settings/blocks/fortune/theme")

        assert response.status_code == 404
        service.get_theme_state.assert_not_awaited()
