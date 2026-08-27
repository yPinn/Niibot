import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx
from openai import (
    APITimeoutError,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam
from pypinyin import lazy_pinyin
from twitchio.ext import commands

from core.component import BotComponent
from core.config import DATA_DIR, get_settings
from core.guards import has_role, is_on_cooldown, record_cooldown
from shared.ai_provider import ProviderEntry, build_provider_chain, call_provider_chain
from shared.packs import Pack, load_packs
from shared.packs import match_entries as match_pack_entries
from shared.repositories.ai_settings import AISettingsRepository, build_system_prompt
from shared.repositories.module_config import ModuleConfigRepository

if TYPE_CHECKING:
    from core.bot import Bot
else:
    from twitchio.ext.commands import Bot


@dataclass
class _Cooldown:
    cooldown: int | None


LOGGER: logging.Logger = logging.getLogger(__name__)

_CHAT_FILTER_PATH = DATA_DIR / "chat_filter.json"

_FALLBACK_SUBSTRINGS: list[str] = ["尼哥", "黑鬼"]
_FALLBACK_PINYIN: list[str] = ["nige", "heigui"]


def _load_chat_filter() -> tuple[list[str], list[str]]:
    substrings: list[str] = _FALLBACK_SUBSTRINGS
    pinyin_patterns: list[str] = _FALLBACK_PINYIN
    try:
        with open(_CHAT_FILTER_PATH, encoding="utf-8") as f:
            data = json.load(f)
        substrings = data.get("substrings", _FALLBACK_SUBSTRINGS)
        pinyin_patterns = data.get("pinyin", _FALLBACK_PINYIN)
        LOGGER.info(
            f"chat_filter.json loaded: {len(substrings)} substrings, {len(pinyin_patterns)} pinyin"
        )
    except FileNotFoundError:
        LOGGER.warning("chat_filter.json not found, using hardcoded fallback")
    except Exception as e:
        LOGGER.warning(f"Failed to load chat_filter.json: {e}, using hardcoded fallback")
    return substrings, pinyin_patterns


_FLAGGED_SUBSTRINGS, _FLAGGED_PINYIN = _load_chat_filter()

_PACKS: dict[str, Pack] = load_packs(DATA_DIR)


# Dialect confusion pairs applied before pinyin matching.
# Each tuple is (source, replacement); order matters.
_PINYIN_NORM: list[tuple[str, str]] = [
    ("l", "n"),  # l/n confusion common in many Mandarin dialects (哩哥 → nige)
]


def _to_flat_pinyin(text: str) -> str:
    """Convert Chinese characters to concatenated tone-less lowercase pinyin."""
    return "".join(lazy_pinyin(text)).lower()


def _normalize_pinyin(p: str) -> str:
    for src, dst in _PINYIN_NORM:
        p = p.replace(src, dst)
    return p


def _scan_response(text: str) -> str | None:
    """Return a description of the matched pattern if flagged content is found, else None."""
    for pattern in _FLAGGED_SUBSTRINGS:
        if pattern in text:
            return pattern

    if not _FLAGGED_PINYIN:
        return None
    pinyin = _normalize_pinyin(_to_flat_pinyin(text))
    for pattern in _FLAGGED_PINYIN:
        if pattern in pinyin:
            return f"pinyin:{pattern}"

    return None


class AIComponent(BotComponent):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self.ai_settings_repo = AISettingsRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.module_config_repo = ModuleConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]

        settings = get_settings()
        self.provider_chain: list[ProviderEntry] = build_provider_chain(
            groq_api_key=settings.groq_api_key,
            groq_model=settings.groq_model,
            gemini_api_key=settings.gemini_api_key,
            gemini_model=settings.gemini_model,
            openrouter_api_key=settings.openrouter_api_key,
            openrouter_model=settings.openrouter_model,
            data_dir=DATA_DIR,
            timeout=20.0,
            provider_order=("groq", "gemini", "openrouter"),  # speed-first for live chat
        )
        LOGGER.info(f"AIComponent initialized: {len(self.provider_chain)} provider entries")

    def refresh_pool(self, pool) -> None:
        self.ai_settings_repo.pool = pool
        self.module_config_repo.pool = pool

    async def sync_emotes(self, channel_id: str) -> None:
        """Refresh enabled_emotes after bot mod status changes.

        Calls chat/emotes/user with broadcaster_id so mod-granted access is
        reflected, then updates ai_settings and notifies the bot to reload.
        """
        settings = get_settings()
        token_row = await self.bot.channels.get_token(settings.bot_id, "bot")
        if not token_row:
            LOGGER.warning("[%s] emote sync skipped: no bot token", channel_id)
            return
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    "https://api.twitch.tv/helix/chat/emotes/user",
                    headers={
                        "Client-Id": settings.twitch_client_id,
                        "Authorization": f"Bearer {token_row.token}",
                    },
                    params={"user_id": settings.bot_id, "broadcaster_id": channel_id},
                )
            if r.status_code != 200:
                LOGGER.warning("[%s] emote sync API error: %s", channel_id, r.status_code)
                return

            emotes = r.json().get("data", [])
            channel_names = [
                e["name"] for e in emotes if e.get("emote_type") not in ("globals", "smilies")
            ]
            global_names = [e["name"] for e in emotes if e.get("emote_type") == "globals"]
            available = channel_names + global_names

            current = await self.ai_settings_repo.get(channel_id)
            if set(current.get("enabled_emotes") or []) == set(available):
                return

            await self.ai_settings_repo.upsert(channel_id, enabled_emotes=available)
            payload = json.dumps({"channel_id": channel_id, "table": "ai_settings"})
            async with self.bot.token_database.acquire() as conn:
                await conn.execute("SELECT pg_notify('config_change', $1)", payload)
            LOGGER.info("[%s] emote sync: %d emotes updated", channel_id, len(available))
        except Exception:
            LOGGER.exception("[%s] emote sync failed", channel_id)

    @commands.command(aliases=["問"])
    async def ai(self, ctx: commands.Context[Bot], *, message: str | None = None) -> None:
        """Ask AI a question (text only).

        Usage:
            !ai <question>

        Examples:
            !ai 今天天氣如何？
            !ai 你好嗎？
        """
        ai_settings = await self.ai_settings_repo.get(ctx.channel.id)
        if not ai_settings.get("enabled", False):
            return
        if not has_role(ctx.chatter, ai_settings.get("min_role", "everyone")):
            return
        if is_on_cooldown(
            ctx.channel.id, "ai", _Cooldown(cooldown=ai_settings.get("cooldown", 15))
        ):
            return

        if not message or not message.strip():
            await self._ctx_reply(ctx, "用法：!ai <問題>")
            return

        record_cooldown(ctx.channel.id, "ai")

        try:
            LOGGER.debug(
                f"AI request: channel={ctx.channel.name}, user={ctx.chatter.name}, message={message[:100]}"
            )

            enabled_packs = await self.module_config_repo.get_enabled_packs()
            matched = match_pack_entries(_PACKS, enabled_packs, message) if enabled_packs else []

            messages: list[ChatCompletionMessageParam] = [
                {"role": "system", "content": build_system_prompt(ai_settings, matched)},
                {"role": "user", "content": message},
            ]

            response, last_error = await call_provider_chain(
                self.provider_chain, messages, max_tokens=ai_settings["max_tokens"]
            )

            # Twitch message limit is 500 characters — truncate at sentence boundary
            if len(response) > 500:
                truncated = response[:497]
                for punct in ("。", "！", "？", "!", "?", "."):
                    pos = truncated.rfind(punct)
                    if pos > len(truncated) // 2:  # must keep at least half the text
                        response = truncated[: pos + 1]
                        break
                else:
                    response = truncated + "…"

            if response:
                flagged = _scan_response(response)
                if flagged:
                    LOGGER.warning(
                        f"[{ctx.channel.name}] AI response blocked — flagged substring: {flagged!r}"
                    )
                    await self._ctx_reply(
                        ctx, "訊號不穩，剛才那句話被宇宙射線干擾掉了，換個問題試試？"
                    )
                    return
                await self._ctx_reply(ctx, response)
            elif last_error:
                raise last_error
            else:
                LOGGER.warning("Empty content after all models")
                await self._ctx_reply(ctx, "AI 回應為空，請重試")
        except RateLimitError as e:
            await self._ctx_reply(ctx, "服務繁忙，請稍後再試")
            LOGGER.warning(f"[{ctx.channel.name}] AI rate limit: {e}")
        except PermissionDeniedError as e:
            await self._ctx_reply(ctx, "服務異常，請聯絡管理員")
            LOGGER.error(f"[{ctx.channel.name}] AI permission denied: {e}")
        except AuthenticationError as e:
            await self._ctx_reply(ctx, "設定異常，請聯絡管理員")
            LOGGER.error(f"[{ctx.channel.name}] AI authentication error: {e}")
        except APITimeoutError as e:
            await self._ctx_reply(ctx, "回應逾時，請稍後再試")
            LOGGER.warning(f"[{ctx.channel.name}] AI timeout: {e}")
        except Exception as e:
            await self._ctx_reply(ctx, "服務暫時異常，請稍後再試")
            LOGGER.error(f"[{ctx.channel.name}] AI unexpected error ({type(e).__name__}): {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(AIComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
