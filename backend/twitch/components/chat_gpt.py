import os
import logging
from typing import TYPE_CHECKING, Optional

from openai import OpenAI
from twitchio.ext import commands

if TYPE_CHECKING:
    from main import Bot
else:
    from twitchio.ext.commands import Bot


LOGGER: logging.Logger = logging.getLogger("AIComponent")


class AIComponent(commands.Component):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

        # Validate required environment variables
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        model = os.getenv("OPENROUTER_MODEL", "")

        if not api_key or api_key.strip() == "":
            raise ValueError("OPENROUTER_API_KEY is required but not set in .env file")

        if not model or model.strip() == "":
            raise ValueError("OPENROUTER_MODEL is required but not set in .env file")

        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        self.model = model

        LOGGER.info(f"AIComponent initialized with model: {model}")

    @commands.cooldown(rate=1, per=10)
    @commands.command()
    async def ai(
        self, ctx: commands.Context[Bot], *, message: Optional[str] = None
    ) -> None:
        """Ask AI a question (text only).

        Usage:
            !ai <question>

        Examples:
            !ai 今天天氣如何？
            !ai 你好嗎？
        """
        if not message or not message.strip():
            await ctx.reply("用法: !ai <問題>")
            return

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                # Limit response length (Twitch has 500 char limit anyway)
                max_tokens=500,
                messages=[
                    {
                        "role": "system",
                        "content": """你是一個友善的 Twitch 聊天機器人助手。請遵守以下規範：
                        1. 使用繁體中文回答，保持簡潔友善的語氣
                        2. 盡量在 50-100 字內簡短回答，最多不超過 150 字
                        3. 嚴格遵守 Twitch 社群規範：
                            - 禁止任何形式的仇恨言論、歧視性內容（種族、性別、宗教、性取向等）
                            - 禁止暴力、威脅或騷擾內容
                            - 禁止成人或露骨的性內容
                            - 禁止非法活動或危險行為的推廣
                            - 保持尊重和包容的態度
                        4. 如果問題涉及不當內容，禮貌地拒絕回答
                        5. 提供有幫助、正面且安全的回應
                        """,
                    },
                    {"role": "user", "content": message},
                ],
            )

            response = completion.choices[0].message.content or ""
            # Twitch message limit is 500 characters
            if len(response) > 500:
                response = response[:497] + "..."

            await ctx.reply(response if response else "無法生成回應")
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
