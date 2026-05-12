import json
import logging
from typing import TYPE_CHECKING

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
from core.guards import check_command
from shared.ai_provider import ProviderEntry, build_provider_chain, call_provider_chain
from shared.repositories.command_config import CommandConfigRepository

if TYPE_CHECKING:
    from core.bot import Bot
else:
    from twitchio.ext.commands import Bot


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


_SYSTEM_PROMPT = (
    "你是 Twitch 聊天室機器人，回應直接顯示於公開直播聊天室，須符合 Twitch 服務條款。\n\n"
    "格式：\n"
    "- 語言：繁體中文（除非使用者明確要求其他語言）\n"
    "- 長度：最多100字，1-2句完整句子\n"
    "- 一段連貫文字，禁止換行，禁止 Markdown 符號（**、*、#、_、- 等）\n"
    "- 直接回答，不輸出思考過程\n"
    "- 人名、地名等專有名詞請附上英文原名或優先使用英文（例：Copernicus、Newton），"
    "避免中文字元組合意外觸發平台自動過濾器\n\n"
    "平台限制：禁止生成仇恨攻擊、性相關、或針對特定人的騷擾威脅等內容；"
    "遇此類請求請用冷幽默方式婉拒（例如假裝系統錯誤、自稱腦袋當機、或用無辜語氣說做不到），"
    "不要直接說「我無法回答」。知識、遊戲、娛樂等一般問題請正常回答。"
)


class AIComponent(BotComponent):
    COMMANDS: list[dict] = [
        {"command_name": "ai", "cooldown": 15, "aliases": "問"},
    ]

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self.cmd_repo = CommandConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.channel_repo = self.bot.channels  # type: ignore[attr-defined]

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
        self.cmd_repo.pool = pool

    @commands.command(aliases=["問"])
    async def ai(self, ctx: commands.Context[Bot], *, message: str | None = None) -> None:
        """Ask AI a question (text only).

        Usage:
            !ai <question>

        Examples:
            !ai 今天天氣如何？
            !ai 你好嗎？
        """
        config = await check_command(self.cmd_repo, ctx, "ai", self.channel_repo)
        if not config:
            return

        if not message or not message.strip():
            await self._ctx_reply(ctx, "用法：!ai <問題>")
            return

        try:
            LOGGER.debug(
                f"AI request: channel={ctx.channel.name}, user={ctx.chatter.name}, message={message[:100]}"
            )

            messages: list[ChatCompletionMessageParam] = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ]

            response, last_error = await call_provider_chain(
                self.provider_chain, messages, max_tokens=250
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
                try:
                    await self.cmd_repo.increment_usage_count(ctx.channel.id, "ai")
                except Exception as e:
                    LOGGER.debug(f"[{ctx.channel.name}] Failed to record AI usage count: {e}")
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
