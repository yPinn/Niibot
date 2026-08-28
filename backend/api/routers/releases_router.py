"""GitHub releases proxy endpoint."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from core.config import get_settings
from shared.errors import NotFoundError, UpstreamError

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/releases", tags=["releases"])

_GITHUB_REPO = "yPinn/Niibot"
_GITHUB_API_URL = f"https://api.github.com/repos/{_GITHUB_REPO}/releases"


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


class GithubRelease(BaseModel):
    id: int
    tag_name: str
    name: str | None = None
    body: str | None = None
    published_at: str
    prerelease: bool
    draft: bool


@router.get("", response_model=list[GithubRelease])
async def get_releases() -> list[GithubRelease]:
    """Proxy GitHub releases for the private repo, injecting a server-side PAT."""
    settings = get_settings()

    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if settings.releases_github_token:
        headers["Authorization"] = f"Bearer {settings.releases_github_token}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{_GITHUB_API_URL}?per_page=30", headers=headers)
    except httpx.TimeoutException as exc:
        raise ReleasesTimeoutError() from exc

    if response.status_code == 404:
        raise ReleasesNotFoundError()
    if not response.is_success:
        raise ReleasesUpstreamError(context={"github_status": response.status_code})

    return [GithubRelease(**r) for r in response.json() if not r.get("draft")]
