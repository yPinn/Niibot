"""AI settings API routes — per-channel AI character configuration."""

from __future__ import annotations

import json
import logging
from typing import Literal

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.config import Settings, get_settings
from core.dependencies import get_current_channel_id, get_db_pool, get_twitch_api
from services.twitch_api import TwitchAPIClient
from shared.repositories.ai_settings import DEFAULT_AI_SETTINGS, AISettingsRepository
from shared.repositories.channel import ChannelRepository

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


class AISettingsResponse(BaseModel):
    bot_name: str
    persona: str
    response_lang: str
    refusal_style: str
    max_tokens: int
    enabled_emotes: list[str]
    enabled: bool
    cooldown: int
    min_role: str


class AISettingsPatch(BaseModel):
    bot_name: str | None = Field(None, min_length=1, max_length=50)
    persona: str | None = Field(None, max_length=300)
    response_lang: Literal["zh-tw", "en", "auto"] | None = None
    refusal_style: Literal["humorous", "polite"] | None = None
    max_tokens: int | None = Field(None, ge=50, le=500)
    enabled_emotes: list[str] | None = None
    enabled: bool | None = None
    cooldown: int | None = Field(None, ge=5, le=300)
    min_role: Literal["everyone", "subscriber", "vip", "moderator", "broadcaster"] | None = None


class EmoteItem(BaseModel):
    id: str
    name: str
    url: str
    emote_type: str = "globals"
    tier: str = ""
    available: bool = True
    animated: bool = False


async def _notify(pool: asyncpg.Pool, channel_id: str) -> None:
    payload = json.dumps({"channel_id": channel_id, "table": "ai_settings"})
    async with pool.acquire() as conn:
        await conn.execute("SELECT pg_notify('config_change', $1)", payload)


@router.get("/settings", response_model=AISettingsResponse)
async def get_ai_settings(
    channel_id: str = Depends(get_current_channel_id),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> AISettingsResponse:
    """Return current AI settings for the authenticated channel."""
    try:
        settings = await AISettingsRepository(pool).get(channel_id)
        return AISettingsResponse(**settings)
    except Exception:
        LOGGER.exception("Failed to get AI settings")
        raise HTTPException(status_code=500, detail="Failed to fetch AI settings") from None


@router.patch("/settings", response_model=AISettingsResponse)
async def patch_ai_settings(
    body: AISettingsPatch,
    channel_id: str = Depends(get_current_channel_id),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> AISettingsResponse:
    """Update one or more AI settings fields for the authenticated channel."""
    try:
        patch = body.model_dump(exclude_none=True)
        if not patch:
            raise HTTPException(status_code=422, detail="No fields provided")

        result = await AISettingsRepository(pool).upsert(channel_id, **patch)
        await _notify(pool, channel_id)

        LOGGER.info(f"Channel {channel_id} updated AI settings: {list(patch)}")
        return AISettingsResponse(**result)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to update AI settings")
        raise HTTPException(status_code=500, detail="Failed to update AI settings") from None


@router.post("/settings/reset", response_model=AISettingsResponse)
async def reset_ai_settings(
    channel_id: str = Depends(get_current_channel_id),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> AISettingsResponse:
    """Reset all AI settings to factory defaults."""
    try:
        result = await AISettingsRepository(pool).upsert(channel_id, **DEFAULT_AI_SETTINGS)
        await _notify(pool, channel_id)

        LOGGER.info(f"Channel {channel_id} reset AI settings to defaults")
        return AISettingsResponse(**result)
    except Exception:
        LOGGER.exception("Failed to reset AI settings")
        raise HTTPException(status_code=500, detail="Failed to reset AI settings") from None


@router.get("/emotes", response_model=list[EmoteItem])
async def get_ai_emotes(
    channel_id: str = Depends(get_current_channel_id),
    pool: asyncpg.Pool = Depends(get_db_pool),
    twitch: TwitchAPIClient = Depends(get_twitch_api),
    settings: Settings = Depends(get_settings),
) -> list[EmoteItem]:
    """Return all channel + global emotes with bot availability status.

    Availability is determined by fetching the bot's accessible emotes via its user token
    (requires user:read:emotes scope). Falls back to unavailable for subscription/bits
    emotes if the bot token is missing or the scope is not yet granted.
    """
    import asyncio

    bot_token: str | None = None
    if settings.bot_id:
        token_row = await ChannelRepository(pool).get_token(settings.bot_id, "bot")
        if token_row:
            bot_token = token_row.token

    try:
        coros: list = [twitch.get_global_emotes(), twitch.get_channel_emotes(channel_id)]
        if bot_token:
            coros.append(twitch.get_user_emotes(channel_id, bot_token, settings.bot_id))

        results = await asyncio.gather(*coros)
        global_raw: list[dict] = results[0]
        channel_raw: list[dict] = results[1]
        user_raw: list[dict] = results[2] if bot_token else []

        accessible: set[str] | None = {e["id"] for e in user_raw} if bot_token else None

        def is_available(e: dict) -> bool:
            if e.get("emote_type") in ("globals", "follower"):
                return True
            return e["id"] in accessible if accessible is not None else False

        items = [
            EmoteItem(
                id=e["id"],
                name=e["name"],
                url=e["url"],
                emote_type=e.get("emote_type", ""),
                tier=e.get("tier", ""),
                available=is_available(e),
                animated=e.get("animated", False),
            )
            for e in channel_raw
        ] + [
            EmoteItem(
                id=e["id"],
                name=e["name"],
                url=e["url"],
                emote_type="globals",
                available=True,
                animated=e.get("animated", False),
            )
            for e in global_raw
        ]

        # Sync available emote names → enabled_emotes in DB so the bot prompt stays current.
        # Only write + notify when the list actually changes to avoid unnecessary cache churn.
        available_names = sorted(e.name for e in items if e.available)
        repo = AISettingsRepository(pool)
        current = await repo.get(channel_id)
        if sorted(current.get("enabled_emotes") or []) != available_names:
            await repo.upsert(channel_id, enabled_emotes=available_names)
            await _notify(pool, channel_id)
            LOGGER.info(
                "Channel %s: synced %d available emotes → enabled_emotes",
                channel_id,
                len(available_names),
            )

        return items
    except Exception:
        LOGGER.exception("Failed to fetch emotes for channel %s", channel_id)
        raise HTTPException(status_code=500, detail="Failed to fetch emotes") from None
