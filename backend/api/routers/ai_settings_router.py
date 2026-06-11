"""AI settings API routes — per-channel AI character configuration."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Literal

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from core.config import DATA_DIR, Settings, get_settings
from core.dependencies import get_current_channel_id, get_db_pool, get_twitch_api
from services.twitch_api import TwitchAPIClient
from shared.packs import Pack, load_packs
from shared.repositories.ai_settings import DEFAULT_AI_SETTINGS, AISettingsRepository
from shared.repositories.channel import ChannelRepository

_PACKS: dict[str, Pack] = {}


def _get_packs() -> dict[str, Pack]:
    """Lazy-load available packs from disk (for the /packs listing endpoint)."""
    global _PACKS
    if not _PACKS:
        _PACKS = load_packs(DATA_DIR)
    return _PACKS


LOGGER: logging.Logger = logging.getLogger(__name__)

# ── Persona bias detection ───────────────────────────────────────────────────
# Catches obvious discriminatory framing in persona/catchphrase text.
# Implicit bias that slips through is handled by _CHANNEL_POLICY in the prompt.

_IDENTITY_TERMS = (
    r"黑人|白人|亞裔|亞洲人|台灣人|中國人|日本人|韓國人|外國人|移民|難民"
    r"|穆斯林|基督徒|猶太|佛教|印度教"
    r"|同性戀|LGBT|跨性別|女人|男人|女性|男性"
    r"|殘障|身障|精神病|精神障礙"
    r"|窮人|低收入|有錢人|富人"
)
_NEGATIVE_ATTRS = r"笨|蠢|懶|髒|醜|壞|危險|低劣|劣等|下賤|噁心|骯髒|素質差|沒水準|賤"
_ATTITUDE_VERBS = r"歧視|看不起|討厭|嫌棄|瞧不起|排斥|鄙視|仇恨|恨"

_BIAS_PATTERNS: list[re.Pattern[str]] = [
    # explicit negative attitude toward identity group
    re.compile(rf"({_ATTITUDE_VERBS}).{{0,20}}({_IDENTITY_TERMS})", re.IGNORECASE),
    re.compile(rf"({_IDENTITY_TERMS}).{{0,20}}({_ATTITUDE_VERBS})", re.IGNORECASE),
    # group generalisation with negative attribute
    re.compile(
        rf"({_IDENTITY_TERMS}).{{0,15}}(都|通常|一般|本來就|天生).{{0,15}}({_NEGATIVE_ATTRS})",
        re.IGNORECASE,
    ),
    # inferiority comparison
    re.compile(rf"比.{{1,15}}(更|還)({_NEGATIVE_ATTRS})", re.IGNORECASE),
]


def _contains_bias(text: str) -> bool:
    """Return True if text matches any obvious discriminatory pattern."""
    return any(p.search(text) for p in _BIAS_PATTERNS)


router = APIRouter(prefix="/api/ai", tags=["ai"])


class AISettingsResponse(BaseModel):
    bot_name: str
    persona: str
    self_pronoun: str
    catchphrase: str
    response_lang: str
    refusal_style: str
    max_tokens: int
    enabled_emotes: list[str]
    enabled: bool
    cooldown: int
    min_role: str


class PackInfo(BaseModel):
    id: str
    name: str
    description: str


class AISettingsPatch(BaseModel):
    bot_name: str | None = Field(None, min_length=1, max_length=50)
    persona: str | None = Field(None, max_length=300)
    self_pronoun: str | None = Field(None, max_length=20)
    catchphrase: str | None = Field(None, max_length=50)
    response_lang: Literal["zh-tw", "en", "auto"] | None = None
    refusal_style: Literal["humorous", "polite"] | None = None
    max_tokens: int | None = Field(None, ge=50, le=500)
    enabled_emotes: list[str] | None = None
    enabled: bool | None = None
    cooldown: int | None = Field(None, ge=5, le=300)
    min_role: Literal["everyone", "subscriber", "vip", "moderator", "broadcaster"] | None = None

    @field_validator("persona", "catchphrase", mode="before")
    @classmethod
    def reject_biased_text(cls, v: object) -> object:
        if isinstance(v, str) and _contains_bias(v):
            raise ValueError("內容含有歧視性或偏見性語句，請修改後重試")
        return v


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


async def _sync_emotes(pool: asyncpg.Pool, channel_id: str, available_names: list[str]) -> None:
    """Background task: persist available emote names so the bot prompt stays current."""
    try:
        repo = AISettingsRepository(pool)
        current = await repo.get(channel_id)
        if set(current.get("enabled_emotes") or []) != set(available_names):
            await repo.upsert(channel_id, enabled_emotes=available_names)
            await _notify(pool, channel_id)
            LOGGER.info(
                "Channel %s: synced %d available emotes → enabled_emotes",
                channel_id,
                len(available_names),
            )
    except Exception:
        LOGGER.exception("Background emote sync failed for channel %s", channel_id)


@router.get("/packs", response_model=list[PackInfo])
async def get_ai_packs() -> list[PackInfo]:
    """Return all available knowledge packs (loaded from disk at first call)."""
    packs = _get_packs()
    return [PackInfo(id=p.id, name=p.name, description=p.description) for p in packs.values()]


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

        LOGGER.info("Channel %s updated AI settings: %s", channel_id, list(patch))
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
    """Reset user-configurable AI settings to factory defaults.

    enabled_emotes is excluded — it is bot-managed and re-synced automatically
    when the emotes page is visited; resetting it would cause a temporary gap.
    """
    try:
        reset_data = {k: v for k, v in DEFAULT_AI_SETTINGS.items() if k != "enabled_emotes"}
        result = await AISettingsRepository(pool).upsert(channel_id, **reset_data)
        await _notify(pool, channel_id)

        LOGGER.info("Channel %s reset AI settings to defaults", channel_id)
        return AISettingsResponse(**result)
    except Exception:
        LOGGER.exception("Failed to reset AI settings")
        raise HTTPException(status_code=500, detail="Failed to reset AI settings") from None


@router.get("/emotes", response_model=list[EmoteItem])
async def get_ai_emotes(
    background_tasks: BackgroundTasks,
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
            if e.get("emote_type") == "globals":
                return True
            if accessible is not None:
                return e["id"] in accessible
            return e.get("emote_type") == "follower"

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

        channel_names = [e.name for e in items if e.available and e.emote_type != "globals"]
        global_names = [e.name for e in items if e.available and e.emote_type == "globals"]
        available_names = channel_names + global_names
        background_tasks.add_task(_sync_emotes, pool, channel_id, available_names)
        return items
    except Exception:
        LOGGER.exception("Failed to fetch emotes for channel %s", channel_id)
        raise HTTPException(status_code=500, detail="Failed to fetch emotes") from None
