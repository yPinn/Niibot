"""Tests for api.routers.releases_router."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")

from core.config import get_settings  # noqa: E402
from core.error_handlers import register_exception_handlers  # noqa: E402
from routers.releases_router import router as _releases_router  # noqa: E402
from services.github_releases import (  # noqa: E402
    GithubRelease,
    GitHubReleasesNotFoundError,
    GitHubReleasesTimeoutError,
    GitHubReleasesUpstreamError,
)

_RELEASE_PAYLOAD = [
    GithubRelease(
        id=1,
        tag_name="v1.2.3",
        name="Release 1.2.3",
        body="Changelog",
        published_at="2024-01-01T00:00:00Z",
        prerelease=False,
        draft=False,
    ),
    GithubRelease(
        id=2,
        tag_name="v1.2.4-rc",
        name="RC Build",
        body=None,
        published_at="2024-01-02T00:00:00Z",
        prerelease=True,
        draft=False,
    ),
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
    register_exception_handlers(app)
    app.include_router(_releases_router)
    return TestClient(app, raise_server_exceptions=False)


class TestGetReleases:
    def test_returns_releases(self):
        get_releases = AsyncMock(return_value=_RELEASE_PAYLOAD)
        with patch("routers.releases_router._releases_client.get_releases", get_releases):
            response = _make_client().get("/api/releases")

        assert response.status_code == 200
        assert {item["tag_name"] for item in response.json()} == {"v1.2.3", "v1.2.4-rc"}

    def test_returns_empty_list_when_no_releases(self):
        get_releases = AsyncMock(return_value=[])
        with patch("routers.releases_router._releases_client.get_releases", get_releases):
            response = _make_client().get("/api/releases")

        assert response.status_code == 200
        assert response.json() == []

    def test_github_404_returns_404(self):
        get_releases = AsyncMock(side_effect=GitHubReleasesNotFoundError)
        with patch("routers.releases_router._releases_client.get_releases", get_releases):
            response = _make_client().get("/api/releases")

        assert response.status_code == 404

    def test_github_500_returns_502(self):
        get_releases = AsyncMock(side_effect=GitHubReleasesUpstreamError(500))
        with patch("routers.releases_router._releases_client.get_releases", get_releases):
            response = _make_client().get("/api/releases")

        assert response.status_code == 502

    def test_timeout_returns_504(self):
        get_releases = AsyncMock(side_effect=GitHubReleasesTimeoutError)
        with patch("routers.releases_router._releases_client.get_releases", get_releases):
            response = _make_client().get("/api/releases")

        assert response.status_code == 504

    def test_unexpected_exception_returns_500(self):
        get_releases = AsyncMock(side_effect=RuntimeError("unexpected"))
        with patch("routers.releases_router._releases_client.get_releases", get_releases):
            response = _make_client().get("/api/releases")

        assert response.status_code == 500

    def test_token_is_forwarded_to_shared_client(self):
        captured_token = ""

        async def get_releases(token: str):
            nonlocal captured_token
            captured_token = token
            return []

        settings = MagicMock()
        settings.releases_github_token = "ghp_test_token"
        with (
            patch(
                "routers.releases_router._releases_client.get_releases",
                side_effect=get_releases,
            ),
            patch("routers.releases_router.get_settings", return_value=settings),
        ):
            response = _make_client().get("/api/releases")

        assert response.status_code == 200
        assert captured_token == "ghp_test_token"
