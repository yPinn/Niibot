import json
import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx
from pypinyin import lazy_pinyin
from twitchio.ext import commands

from core.component import BotComponent
from core.config import DATA_DIR, get_settings
from core.guards import has_role, is_on_cooldown, record_cooldown
from shared.assistant import (
    AssistantOutcome,
    AssistantRequest,
    BoundedConversationMemoryStore,
    ConversationKey,
    ConversationTurn,
    FailureKind,
    InputSection,
    InputSectionKind,
    OutputPolicy,
    PromptBudget,
    RouterPolicy,
    build_assistant_harness,
)
from shared.assistant.providers.registry import ProviderConfig, ProviderKind
from shared.packs import Pack, load_packs
from shared.packs import match_entries as match_pack_entries
from shared.repositories.ai_settings import AISettingsRepository, build_assistant_sections
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
        self.memory_store = BoundedConversationMemoryStore(
            ttl_seconds=600,
            max_sessions=500,
            max_turns_per_session=2,
            max_chars_per_session=1_000,
            max_total_chars=500_000,
        )

        settings = get_settings()
        self.harness = build_assistant_harness(
            configs={
                ProviderKind.GROQ: ProviderConfig(
                    settings.groq_api_key,
                    settings.groq_model,
                ),
                ProviderKind.OPENROUTER: ProviderConfig(
                    settings.openrouter_api_key,
                    settings.openrouter_model,
                ),
            },
            provider_order=(ProviderKind.GROQ, ProviderKind.OPENROUTER),
            provider_timeout_seconds=4.0,
            router_policy=RouterPolicy(
                total_timeout_seconds=8.0,
                per_attempt_timeout_seconds=4.0,
                max_attempts=2,
                failure_threshold=2,
                cooldown_seconds=60.0,
            ),
            prompt_budget=PromptBudget(
                max_total_chars=8_000,
                max_persona_chars=1_500,
                max_context_chars=5_000,
                max_history_chars=1_200,
                max_user_chars=500,
            ),
            output_policy=OutputPolicy(max_chars=500),
            scanner=_scan_response,
        )
        labels = [
            f"{spec.kind.value}/{spec.model}"
            for spec in (self.harness.registry.specs if self.harness.registry else ())
        ]
        LOGGER.info("AIComponent initialized: providers=%s", labels)

    def refresh_pool(self, pool) -> None:
        self.ai_settings_repo.pool = pool
        self.module_config_repo.pool = pool

    def ai_health(self) -> dict:
        registry = self.harness.registry
        memory = self.memory_store.stats()
        return {
            "providers": [
                {
                    "provider": registration.kind.value,
                    "state": registration.state.value,
                    "model": registration.model,
                    "reason": registration.reason,
                }
                for registration in (registry.registrations if registry else ())
            ],
            "circuits": [
                {
                    "provider": circuit.provider,
                    "model": circuit.model,
                    "state": circuit.state.value,
                    "consecutive_failures": circuit.consecutive_failures,
                }
                for circuit in self.harness.provider_health()
            ],
            "memory": {
                "active_sessions": memory.active_sessions,
                "total_chars": memory.total_chars,
                "ttl_evictions": memory.ttl_evictions,
                "lru_evictions": memory.lru_evictions,
                "budget_evictions": memory.budget_evictions,
                "oversized_turn_rejections": memory.oversized_turn_rejections,
            },
        }

    def memory_gauges(self) -> dict[str, int]:
        memory = self.memory_store.stats()
        return {"sessions": memory.active_sessions, "chars": memory.total_chars}

    def clear_channel_memory(self, channel_id: str) -> None:
        removed = self.memory_store.clear_channel("twitch", channel_id)
        if removed:
            LOGGER.info(
                "AI short-term memory cleared: channel_id=%s sessions=%d", channel_id, removed
            )

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

        request_id = uuid.uuid4().hex[:16]
        try:
            LOGGER.debug(
                "AI request started: request_id=%s channel_id=%s input_chars=%d",
                request_id,
                ctx.channel.id,
                len(message),
            )

            enabled_packs = await self.module_config_repo.get_enabled_packs()
            matched = match_pack_entries(_PACKS, enabled_packs, message) if enabled_packs else []

            memory_key: ConversationKey | None = None
            history_sections: tuple[InputSection, ...] = ()
            if ai_settings.get("memory_enabled", False):
                raw_participant_id = getattr(ctx.chatter, "id", None)
                participant_id = (
                    raw_participant_id.strip() if isinstance(raw_participant_id, str) else ""
                )
                if participant_id:
                    memory_key = ConversationKey("twitch", str(ctx.channel.id), participant_id)
                    turns = self.memory_store.get(memory_key)
                    if turns:
                        history_sections = (
                            InputSection(
                                InputSectionKind.CONVERSATION_HISTORY,
                                json.dumps(
                                    {
                                        "source": "ephemeral_conversation",
                                        "turns": [
                                            {
                                                "user": turn.user_content,
                                                "assistant": turn.assistant_content,
                                            }
                                            for turn in turns
                                        ],
                                    },
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                ),
                            ),
                        )
            else:
                self.memory_store.clear_channel("twitch", str(ctx.channel.id))

            request = AssistantRequest(
                sections=(
                    *build_assistant_sections(ai_settings, matched),
                    *history_sections,
                    InputSection(InputSectionKind.USER_INPUT, message),
                ),
                max_output_tokens=ai_settings["max_tokens"],
                request_id=request_id,
            )
            response = await self.harness.respond(request)

            generation = response.generation
            usage = generation.usage
            LOGGER.info(
                "AI request completed: request_id=%s outcome=%s provider=%s model=%s "
                "attempts=%d fallbacks=%d latency_ms=%d input_tokens=%s "
                "output_tokens=%s total_tokens=%s",
                request_id,
                response.output.outcome.value,
                generation.provider,
                generation.model,
                len(generation.attempts),
                max(0, len(generation.attempts) - 1),
                sum(attempt.latency_ms for attempt in generation.attempts),
                usage.input_tokens if usage else None,
                usage.output_tokens if usage else None,
                usage.total_tokens if usage else None,
            )

            if response.output.outcome is AssistantOutcome.OK:
                await self._ctx_reply(ctx, response.output.content)
                if memory_key is not None:
                    self.memory_store.append(
                        memory_key,
                        ConversationTurn(message, response.output.content),
                    )
            elif response.output.outcome is AssistantOutcome.BLOCKED:
                LOGGER.warning("AI response blocked: request_id=%s", request_id)
                await self._ctx_reply(ctx, "訊號不穩，剛才那句話被宇宙射線干擾掉了，換個問題試試？")
            elif response.output.outcome is AssistantOutcome.EMPTY:
                await self._ctx_reply(ctx, "AI 回應為空，請重試")
            elif response.output.outcome is AssistantOutcome.MISCONFIGURED:
                await self._ctx_reply(ctx, "設定異常，請聯絡管理員")
            else:
                failure_kind = generation.failure.kind if generation.failure else None
                if failure_kind is FailureKind.RATE_LIMITED:
                    await self._ctx_reply(ctx, "服務繁忙，請稍後再試")
                elif failure_kind is FailureKind.TIMEOUT:
                    await self._ctx_reply(ctx, "回應逾時，請稍後再試")
                else:
                    await self._ctx_reply(ctx, "服務暫時異常，請稍後再試")
        except Exception as error:
            await self._ctx_reply(ctx, "服務暫時異常，請稍後再試")
            LOGGER.error(
                "AI request failed: request_id=%s error_type=%s",
                request_id,
                type(error).__name__,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(AIComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
