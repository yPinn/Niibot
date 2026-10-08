"""Admin: rate-limit snapshots from every service (owner-only).

The API reports its own registry directly; the bots expose theirs on their
internal-network ``/status`` (never through a public endpoint), which this
relays. A bot that is down or slow comes back as ``null`` rather than failing
the whole view.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.config import Settings, get_settings
from core.dependencies import require_owner
from services import cloudflare_usage
from shared.rate_limits import collect_rate_limits

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter()

_BOT_TIMEOUT_SECONDS = 5.0


class RateLimitsResponse(BaseModel):
    api: list[dict[str, Any]]
    twitch: list[dict[str, Any]] | None
    discord: list[dict[str, Any]] | None


async def _bot_rate_limits(client: httpx.AsyncClient, url: str) -> list[dict[str, Any]] | None:
    try:
        response = await client.get(f"{url}/status")
        if response.status_code != 200:
            return None
        limits = response.json().get("rate_limits")
        return limits if isinstance(limits, list) else None
    except Exception:
        LOGGER.debug("Bot rate limits unavailable: %s", url)
        return None


@router.get("/rate-limits", response_model=RateLimitsResponse)
async def get_rate_limits(
    _: str = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> RateLimitsResponse:
    async with httpx.AsyncClient(timeout=_BOT_TIMEOUT_SECONDS) as client:
        twitch, discord = await asyncio.gather(
            _bot_rate_limits(client, settings.twitch_bot_url),
            _bot_rate_limits(client, settings.discord_bot_url),
        )
    return RateLimitsResponse(
        api=[dict(s) for s in collect_rate_limits()],
        twitch=twitch,
        discord=discord,
    )


class CloudflareUsageResponse(BaseModel):
    configured: bool
    limit: int
    day_start: str | None = None
    reset_at: str | None = None
    workers_requests: int | None = None
    pages_requests: int | None = None
    total_requests: int | None = None
    errors: list[str] = []
    fetched_at: str | None = None


@router.get("/cloudflare-usage", response_model=CloudflareUsageResponse)
async def get_cloudflare_usage(
    _: str = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> CloudflareUsageResponse:
    usage = await cloudflare_usage.fetch_usage(
        settings.cloudflare_account_id, settings.cloudflare_api_token
    )
    return CloudflareUsageResponse(
        configured=usage.configured,
        limit=usage.limit,
        day_start=usage.day_start,
        reset_at=usage.reset_at,
        workers_requests=usage.workers_requests,
        pages_requests=usage.pages_requests,
        total_requests=usage.total_requests,
        errors=usage.errors,
        fetched_at=usage.fetched_at,
    )
