"""Tests for api.routers.releases_router."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.config import get_settings
from routers.releases_router import router as _releases_router

_RELEASE_PAYLOAD = [
    {
        "id": 1,
        "tag_name": "v1.2.3",
        "name": "Release 1.2.3",
        "body": "Changelog",
        "published_at": "2024-01-01T00:00:00Z",
        "prerelease": False,
        "draft": False,
    },
    {
        "id": 2,
        "tag_name": "v1.2.4-rc",
        "name": "RC Build",
        "body": None,
        "published_at": "2024-01-02T00:00:00Z",
        "prerelease": True,
        "draft": False,
    },
    {
        "id": 3,
        "tag_name": "v1.2.5-draft",
        "name": "Draft",
        "body": None,
        "published_at": "2024-01-03T00:00:00Z",
        "prerelease": False,
        "draft": True,  # filtered out
    },
]


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_client() -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    app.include_router(_releases_router)
    return TestClient(app, raise_server_exceptions=False)


def _mock_response(status_code: int, json_data=None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.json.return_value = json_data or []
    return resp


# ── GET /api/releases ─────────────────────────────────────────────────────────


class TestGetReleases:
    def test_returns_non_draft_releases(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(200, _RELEASE_PAYLOAD))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("routers.releases_router.httpx.AsyncClient", return_value=mock_client):
            r = _make_client().get("/api/releases")

        assert r.status_code == 200
        data = r.json()
        # draft entries are filtered
        assert len(data) == 2
        tags = {d["tag_name"] for d in data}
        assert "v1.2.3" in tags
        assert "v1.2.4-rc" in tags
        assert "v1.2.5-draft" not in tags

    def test_returns_empty_list_when_no_releases(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(200, []))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("routers.releases_router.httpx.AsyncClient", return_value=mock_client):
            r = _make_client().get("/api/releases")

        assert r.status_code == 200
        assert r.json() == []

    def test_github_404_returns_404(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(404))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("routers.releases_router.httpx.AsyncClient", return_value=mock_client):
            r = _make_client().get("/api/releases")

        assert r.status_code == 404

    def test_github_500_returns_502(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(500))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("routers.releases_router.httpx.AsyncClient", return_value=mock_client):
            r = _make_client().get("/api/releases")

        assert r.status_code == 502

    def test_timeout_returns_504(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("routers.releases_router.httpx.AsyncClient", return_value=mock_client):
            r = _make_client().get("/api/releases")

        assert r.status_code == 504

    def test_unexpected_exception_returns_500(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("unexpected"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("routers.releases_router.httpx.AsyncClient", return_value=mock_client):
            r = _make_client().get("/api/releases")

        assert r.status_code == 500

    def test_token_injected_in_auth_header(self):
        """When RELEASES_GITHUB_TOKEN is set, Authorization header is sent."""
        captured_headers: dict = {}

        async def _fake_get(url, headers=None, **kw):
            captured_headers.update(headers or {})
            return _mock_response(200, [])

        mock_client = AsyncMock()
        mock_client.get = _fake_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        settings_mock = MagicMock()
        settings_mock.releases_github_token = "ghp_test_token"

        with (
            patch("routers.releases_router.httpx.AsyncClient", return_value=mock_client),
            patch("routers.releases_router.get_settings", return_value=settings_mock),
        ):
            _make_client().get("/api/releases")

        assert "Authorization" in captured_headers
        assert "ghp_test_token" in captured_headers["Authorization"]
