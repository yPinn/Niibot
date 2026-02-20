import logging
import re
from typing import TYPE_CHECKING

from openai import OpenAI
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


class AIComponent(commands.Component):
    COMMANDS: list[dict] = [
        {"command_name": "ai", "cooldown": 15},
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

        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        self.model = model

        LOGGER.info(f"AIComponent initialized: model={model}")

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
            for attempt in range(2):
                completion = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=800,
                    messages=messages,
                )

                if not completion.choices:
                    LOGGER.warning(f"AI attempt {attempt + 1}: no choices")
                    continue

                raw = completion.choices[0].message.content or ""
                response = re.sub(r"<think>[\s\S]*?</think>", "", raw)
                response = re.sub(r"<think>[\s\S]*$", "", response)
                response = response.strip()

                LOGGER.info(f"AI attempt {attempt + 1}: raw={len(raw)}, clean={len(response)}")
                if response:
                    break

            # Twitch message limit is 500 characters
            if len(response) > 500:
                response = response[:497] + "..."

            if response:
                await ctx.reply(response)
            else:
                LOGGER.warning("Empty content after 2 attempts")
                await ctx.reply("AI 回應為空，請重試")
        except Exception as e:
            error_msg = str(e)
            # Provide more specific error messages for text-only mode
            if "rate limit" in error_msg.lower() or "429" in error_msg:
                await ctx.reply("API 請求過於頻繁，請稍後再試")
            elif "timeout" in error_msg.lower():
                await ctx.reply("請求超時，請稍後再試")
            elif "authentication" in error_msg.lower() or "401" in error_msg:
                await ctx.reply("API 認證失敗")
            elif "400" in error_msg:
                await ctx.reply("請求格式錯誤，請稍後再試")
            else:
                await ctx.reply("AI 服務暫時無法使用，請稍後再試")
            LOGGER.error(f"AI command error: {error_msg}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(AIComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
