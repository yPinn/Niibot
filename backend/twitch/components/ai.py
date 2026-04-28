import json
import logging
import re
import time
from typing import TYPE_CHECKING

from openai import (
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam
from pypinyin import lazy_pinyin
from twitchio.ext import commands

from core.config import DATA_DIR, get_settings
from core.guards import check_command
from shared.repositories.command_config import CommandConfigRepository

if TYPE_CHECKING:
    from core.bot import Bot
else:
    from twitchio.ext.commands import Bot


LOGGER: logging.Logger = logging.getLogger(__name__)

_THINK_CLOSED = re.compile(r"<think>[\s\S]*?</think>")
_THINK_OPEN = re.compile(r"<think>[\s\S]*$")

_FREE_MODELS_PATH = DATA_DIR / "free_models.json"
_MAX_FALLBACKS = 3


def _load_fallback_models(primary: str) -> list[str]:
    models: list[str] = []
    try:
        with open(_FREE_MODELS_PATH) as f:
            data = json.load(f)
        candidates = [m["id"] for m in data.get("models", []) if m.get("enabled", False)]
        models = [m for m in candidates if m != primary][:_MAX_FALLBACKS]
        LOGGER.info(f"Loaded {len(models)} fallback models from {_FREE_MODELS_PATH.name}")
    except FileNotFoundError:
        LOGGER.warning(f"{_FREE_MODELS_PATH.name} not found, no fallback models available")
    except Exception as e:
        LOGGER.warning(f"Failed to load free_models.json: {e}, no fallback models available")
    return models


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


class AIComponent(commands.Component):
    COMMANDS: list[dict] = [
        {"command_name": "ai", "cooldown": 15, "aliases": "問"},
    ]

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self.cmd_repo = CommandConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.channel_repo = self.bot.channels  # type: ignore[attr-defined]

        settings = get_settings()
        api_key = settings.openrouter_api_key
        model = settings.openrouter_model

        if not api_key or api_key.strip() == "":
            raise ValueError("OPENROUTER_API_KEY is required but not set in .env file")

        if not model or model.strip() == "":
            raise ValueError("OPENROUTER_MODEL is required but not set in .env file")

        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=20.0,
        )
        self.models = [model] + _load_fallback_models(model)

        LOGGER.info(f"AIComponent initialized: primary={model}, fallbacks={len(self.models) - 1}")

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
            await ctx.reply("用法: !ai <問題>")
            return

        try:
            LOGGER.info(
                f"AI request: channel={ctx.channel.name}, user={ctx.chatter.name}, message={message[:100]}"
            )

            messages: list[ChatCompletionMessageParam] = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ]

            response = ""
            last_error: Exception | None = None
            t_start = time.monotonic()

            for model in self.models:
                try:
                    completion = await self.client.chat.completions.create(
                        model=model,
                        max_tokens=250,
                        messages=messages,
                        # Prevent reasoning models (e.g. DeepSeek R1) from
                        # consuming the max_tokens budget on <think> content.
                        extra_body={"include_reasoning": False},
                    )

                    if not completion.choices:
                        LOGGER.warning(f"AI [{model}]: no choices, trying next model")
                        continue

                    raw = completion.choices[0].message.content or ""
                    response = _THINK_CLOSED.sub("", raw)
                    response = _THINK_OPEN.sub("", response)
                    response = response.strip()

                    elapsed = time.monotonic() - t_start
                    LOGGER.info(
                        f"AI [{model}]: {elapsed:.1f}s, raw={len(raw)}, clean={len(response)}"
                    )
                    if response:
                        break
                except RateLimitError as e:
                    LOGGER.warning(f"AI rate limit on {model}, trying next model")
                    last_error = e
                    continue
                except APITimeoutError:
                    LOGGER.warning(f"AI [{model}] timed out, trying next model")
                    continue
                except NotFoundError:
                    LOGGER.warning(f"AI [{model}] not found (404), trying next model")
                    continue
                except Exception as e:
                    LOGGER.warning(f"AI [{model}] error ({type(e).__name__}), trying next model")
                    last_error = e
                    continue

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
                    await ctx.reply("訊號不穩，剛才那句話被宇宙射線干擾掉了，換個問題試試？")
                    return
                await ctx.reply(response)
                try:
                    await self.cmd_repo.increment_usage_count(ctx.channel.id, "ai")
                except Exception:
                    pass
            elif last_error:
                raise last_error
            else:
                LOGGER.warning("Empty content after all models")
                await ctx.reply("AI 回應為空，請重試")
        except RateLimitError as e:
            await ctx.reply("AI 功能目前使用人數過多，請稍後再試")
            LOGGER.warning(f"[{ctx.channel.name}] AI rate limit: {e}")
        except PermissionDeniedError as e:
            await ctx.reply("AI 服務暫時無法使用，請聯絡管理員")
            LOGGER.error(f"[{ctx.channel.name}] AI permission denied: {e}")
        except AuthenticationError as e:
            await ctx.reply("AI 服務設定異常，請聯絡管理員")
            LOGGER.error(f"[{ctx.channel.name}] AI authentication error: {e}")
        except APITimeoutError as e:
            await ctx.reply("AI 回應逾時，請稍後再試")
            LOGGER.warning(f"[{ctx.channel.name}] AI timeout: {e}")
        except Exception as e:
            await ctx.reply("AI 服務暫時無法使用，請稍後再試")
            LOGGER.error(f"[{ctx.channel.name}] AI unexpected error ({type(e).__name__}): {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(AIComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
