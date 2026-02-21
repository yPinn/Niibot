import logging
import re
from typing import TYPE_CHECKING

from openai import (
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    PermissionDeniedError,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam
from twitchio.ext import commands

from core.config import get_settings
from core.guards import check_command
from shared.repositories.command_config import CommandConfigRepository

if TYPE_CHECKING:
    from core.bot import Bot
else:
    from twitchio.ext.commands import Bot


LOGGER: logging.Logger = logging.getLogger("AIComponent")

FALLBACK_MODELS: list[str] = [
    "deepseek/deepseek-r1-0528:free",
    "stepfun/step-3.5-flash:free",
    "z-ai/glm-4.5-air:free",
    "openai/gpt-oss-120b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
]


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
        )
        self.models = [model] + [m for m in FALLBACK_MODELS if m != model]

        LOGGER.info(f"AIComponent initialized: primary={model}, fallbacks={len(self.models) - 1}")

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
            LOGGER.debug(f"AI request: user={ctx.author.name}, message={message[:100]}")

            messages: list[ChatCompletionMessageParam] = [
                {
                    "role": "system",
                    "content": """你是 Twitch 聊天機器人。

                        規則：
                        - 語言：繁體中文
                        - 長度：50-100字，最多150字
                        - 語氣：友善、簡潔
                        - 直接回答問題，不要輸出思考過程

                        禁止內容：
                        - 仇恨言論、歧視（種族/性別/宗教/性取向）
                        - 暴力、威脅、騷擾
                        - 成人/性相關內容
                        - 非法活動

                        遇到不當問題請禮貌拒絕。提供正面、安全的回應。
                        """,
                },
                {"role": "user", "content": message},
            ]

            response = ""
            last_error: Exception | None = None

            for model in self.models:
                try:
                    for attempt in range(2):
                        completion = await self.client.chat.completions.create(
                            model=model,
                            max_tokens=1200,
                            messages=messages,
                        )

                        if not completion.choices:
                            LOGGER.warning(f"AI [{model}] attempt {attempt + 1}: no choices")
                            continue

                        raw = completion.choices[0].message.content or ""
                        response = re.sub(r"<think>[\s\S]*?</think>", "", raw)
                        response = re.sub(r"<think>[\s\S]*$", "", response)
                        response = response.strip()

                        LOGGER.info(
                            f"AI [{model}] attempt {attempt + 1}: raw={len(raw)}, clean={len(response)}"
                        )
                        if response:
                            break

                    if response:
                        break
                except RateLimitError as e:
                    LOGGER.warning(f"AI rate limit on {model}, trying next model")
                    last_error = e
                    continue

            # Twitch message limit is 500 characters
            if len(response) > 500:
                response = response[:497] + "..."

            if response:
                await ctx.reply(response)
            elif last_error:
                raise last_error
            else:
                LOGGER.warning("Empty content after all models")
                await ctx.reply("AI 回應為空，請重試")
        except RateLimitError as e:
            await ctx.reply("AI 功能目前使用人數過多，請稍後再試")
            LOGGER.error(f"AI command error: {e}")
        except PermissionDeniedError as e:
            await ctx.reply("AI 服務暫時無法使用，請聯絡管理員")
            LOGGER.error(f"AI command error: {e}")
        except AuthenticationError as e:
            await ctx.reply("AI 服務設定異常，請聯絡管理員")
            LOGGER.error(f"AI command error: {e}")
        except APITimeoutError as e:
            await ctx.reply("AI 回應逾時，請稍後再試")
            LOGGER.error(f"AI command error: {e}")
        except (BadRequestError, Exception) as e:
            await ctx.reply("AI 服務暫時無法使用，請稍後再試")
            LOGGER.error(f"AI command error: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(AIComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
