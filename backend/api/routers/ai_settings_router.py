"""AI settings API routes — per-channel AI character configuration."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Literal

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field, field_validator

from core.config import DATA_DIR, Settings, get_settings
from core.dependencies import (
    get_current_channel_id,
    get_db_pool,
    get_twitch_api,
    require_activated,
)
from services.emote_sync import (
    available_emote_names,
    is_emote_available,
    notify_config_change,
    sync_enabled_emotes,
)
from services.twitch_api import TwitchAPIClient
from shared.errors import InvalidInputError
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

TonePreset = Literal["neutral", "witty", "energetic", "tsundere", "calm"]
CatchphraseFrequency = Literal["off", "rare", "occasional"]


class AISettingsEmptyPatchError(InvalidInputError):
    code = "AI_SETTINGS.EMPTY_PATCH"
    http_status = 422
    user_message = "沒有要更新的欄位"


class AISettingsResponse(BaseModel):
    bot_name: str
    persona: str
    self_pronoun: str
    audience_reference: str
    tone_preset: TonePreset
    catchphrase: str
    catchphrase_frequency: CatchphraseFrequency
    example_replies: list[str]
    response_lang: str
    refusal_style: str
    max_tokens: int
    enabled_emotes: list[str]
    enabled: bool
    memory_enabled: bool
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
    audience_reference: str | None = Field(None, min_length=1, max_length=20)
    tone_preset: TonePreset | None = None
    catchphrase: str | None = Field(None, max_length=50)
    catchphrase_frequency: CatchphraseFrequency | None = None
    example_replies: list[str] | None = Field(None, max_length=3)
    response_lang: Literal["zh-tw", "en", "auto"] | None = None
    refusal_style: Literal["humorous", "polite"] | None = None
    max_tokens: int | None = Field(None, ge=50, le=500)
    enabled_emotes: list[str] | None = None
    enabled: bool | None = None
    memory_enabled: bool | None = None
    cooldown: int | None = Field(None, ge=5, le=300)
    min_role: Literal["everyone", "subscriber", "vip", "moderator", "broadcaster"] | None = None

    @field_validator("persona", "catchphrase", "audience_reference", mode="before")
    @classmethod
    def reject_biased_text(cls, v: object) -> object:
        if isinstance(v, str) and _contains_bias(v):
            raise ValueError("內容含有歧視性或偏見性語句，請修改後重試")
        return v

    @field_validator("audience_reference")
    @classmethod
    def normalize_audience_reference(cls, v: str | None) -> str | None:
        if v is None:
            return None
        value = v.strip()
        if not value:
            raise ValueError("觀眾稱呼不能為空")
        return value

    @field_validator("example_replies")
    @classmethod
    def validate_example_replies(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned: list[str] = []
        for item in v:
            value = item.strip()
            if not value:
                raise ValueError("示例回覆不能為空")
            if len(value) > 120:
                raise ValueError("每則示例回覆最多 120 字")
            if _contains_bias(value):
                raise ValueError("內容含有歧視性或偏見性語句，請修改後重試")
            cleaned.append(value)
        return cleaned


class EmoteItem(BaseModel):
    id: str
    name: str
    url: str
    emote_type: str = "globals"
    tier: str = ""
    available: bool = True
    animated: bool = False


async def _sync_emotes(pool: asyncpg.Pool, channel_id: str, available_names: list[str]) -> None:
    """Background task: persist available emote names so the bot prompt stays current."""
    try:
        await sync_enabled_emotes(pool, channel_id, available_names)
    except Exception:
        # Background best-effort sync; a failure must not surface anywhere.
        LOGGER.exception("emote_sync_failed")


@router.get("/packs", response_model=list[PackInfo])
async def get_ai_packs() -> list[PackInfo]:
    """Return all available knowledge packs (loaded from disk at first call)."""
    packs = _get_packs()
    return [PackInfo(id=p.id, name=p.name, description=p.description) for p in packs.values()]


@router.get("/settings", response_model=AISettingsResponse)
async def get_ai_settings(
    channel_id: str = Depends(get_current_channel_id),
    pool: asyncpg.Pool = Depends(get_db_pool),
    _: None = Depends(require_activated),
) -> AISettingsResponse:
    """Return current AI settings for the authenticated channel."""
    settings = await AISettingsRepository(pool).get(channel_id)
    return AISettingsResponse(**settings)


@router.patch("/settings", response_model=AISettingsResponse)
async def patch_ai_settings(
    body: AISettingsPatch,
    channel_id: str = Depends(get_current_channel_id),
    pool: asyncpg.Pool = Depends(get_db_pool),
    _: None = Depends(require_activated),
) -> AISettingsResponse:
    """Update one or more AI settings fields for the authenticated channel."""
    patch = body.model_dump(exclude_none=True)
    if not patch:
        raise AISettingsEmptyPatchError()

    result = await AISettingsRepository(pool).upsert(channel_id, **patch)
    await notify_config_change(pool, channel_id)

    LOGGER.info("ai_settings_updated", extra={"fields": list(patch)})
    return AISettingsResponse(**result)


@router.post("/settings/reset", response_model=AISettingsResponse)
async def reset_ai_settings(
    channel_id: str = Depends(get_current_channel_id),
    pool: asyncpg.Pool = Depends(get_db_pool),
    _: None = Depends(require_activated),
) -> AISettingsResponse:
    """Reset user-configurable AI settings to factory defaults.

    enabled_emotes is excluded — it is bot-managed and re-synced automatically
    when the emotes page is visited; resetting it would cause a temporary gap.
    """
    reset_data = {k: v for k, v in DEFAULT_AI_SETTINGS.items() if k != "enabled_emotes"}
    result = await AISettingsRepository(pool).upsert(channel_id, **reset_data)
    await notify_config_change(pool, channel_id)

    LOGGER.info("ai_settings_reset")
    return AISettingsResponse(**result)


@router.get("/emotes", response_model=list[EmoteItem])
async def get_ai_emotes(
    background_tasks: BackgroundTasks,
    channel_id: str = Depends(get_current_channel_id),
    pool: asyncpg.Pool = Depends(get_db_pool),
    twitch: TwitchAPIClient = Depends(get_twitch_api),
    settings: Settings = Depends(get_settings),
    _: None = Depends(require_activated),
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

    coros: list = [twitch.get_global_emotes(), twitch.get_channel_emotes(channel_id)]
    if bot_token:
        coros.append(twitch.get_user_emotes(channel_id, bot_token, settings.bot_id))

    results = await asyncio.gather(*coros)
    global_raw: list[dict] = results[0]
    channel_raw: list[dict] = results[1]
    user_raw: list[dict] = results[2] if bot_token else []

    accessible: set[str] | None = {e["id"] for e in user_raw} if bot_token else None

    items = [
        EmoteItem(
            id=e["id"],
            name=e["name"],
            url=e["url"],
            emote_type=e.get("emote_type", ""),
            tier=e.get("tier", ""),
            available=is_emote_available(e, accessible),
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

    available_names = available_emote_names(channel_raw, global_raw, accessible)
    background_tasks.add_task(_sync_emotes, pool, channel_id, available_names)
    return items
