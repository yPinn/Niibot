"""GitHub releases proxy endpoint."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.config import get_settings

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/releases", tags=["releases"])

_GITHUB_REPO = "yPinn/Niibot"
_GITHUB_API_URL = f"https://api.github.com/repos/{_GITHUB_REPO}/releases"


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

        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Repository not found or no releases")
        if not response.is_success:
            LOGGER.error("GitHub API returned %s", response.status_code)
            raise HTTPException(status_code=502, detail="GitHub API error")

        return [GithubRelease(**r) for r in response.json() if not r.get("draft")]

    except HTTPException:
        raise
    except httpx.TimeoutException:
        LOGGER.error("GitHub API timeout")
        raise HTTPException(status_code=504, detail="GitHub API timeout") from None
    except Exception:
        LOGGER.exception("Unexpected error fetching releases")
        raise HTTPException(status_code=500, detail="Failed to fetch releases") from None
