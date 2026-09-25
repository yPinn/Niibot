"""GitHub releases proxy endpoint."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter

from core.config import get_settings
from services.github_releases import (
    GithubRelease,
    GitHubReleasesAuthError,
    GitHubReleasesClient,
    GitHubReleasesNotFoundError,
    GitHubReleasesTimeoutError,
    GitHubReleasesUpstreamError,
)
from shared.errors import NotFoundError, UpstreamError

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/releases", tags=["releases"])

_releases_client = GitHubReleasesClient(httpx.AsyncClient(timeout=10.0))


class ReleasesNotFoundError(NotFoundError):
    code = "RELEASES.NOT_FOUND"
    user_message = "找不到版本資訊"


class ReleasesUpstreamError(UpstreamError):
    code = "RELEASES.UPSTREAM_FAILED"
    user_message = "版本資訊暫時抓不到，請稍後再試"


class ReleasesTimeoutError(UpstreamError):
    code = "RELEASES.UPSTREAM_TIMEOUT"
    http_status = 504
    user_message = "版本資訊載入逾時，請稍後再試"


async def close_releases_http_client() -> None:
    """Close the shared GitHub client during application shutdown."""
    await _releases_client.aclose()


@router.get("", response_model=list[GithubRelease])
async def get_releases() -> list[GithubRelease]:
    """Return cached GitHub releases, injecting the server-side PAT upstream."""
    settings = get_settings()
    try:
        return await _releases_client.get_releases(settings.releases_github_token)
    except GitHubReleasesNotFoundError as exc:
        raise ReleasesNotFoundError() from exc
    except GitHubReleasesTimeoutError as exc:
        raise ReleasesTimeoutError() from exc
    except GitHubReleasesAuthError as exc:
        raise ReleasesUpstreamError(context={"github_status": 401}) from exc
    except GitHubReleasesUpstreamError as exc:
        context = {"github_status": exc.status_code} if exc.status_code is not None else None
        raise ReleasesUpstreamError(context=context) from exc
