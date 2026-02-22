"""AI chat commands using OpenRouter API"""

import json
import logging
import os
import re

import discord
from discord import app_commands
from discord.ext import commands
from openai import (
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    PermissionDeniedError,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam

from core import DATA_DIR

LOGGER = logging.getLogger("AI")

FALLBACK_MODELS: list[str] = [
    "deepseek/deepseek-r1-0528:free",
    "stepfun/step-3.5-flash:free",
    "z-ai/glm-4.5-air:free",
    "openai/gpt-oss-120b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
]


class AI(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        api_key = os.getenv("OPENROUTER_API_KEY", "")
        model = os.getenv("OPENROUTER_MODEL", "openrouter/free")

        if not api_key or api_key.strip() == "":
            raise ValueError("OPENROUTER_API_KEY is required but not set in .env file")

        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=45.0,
        )
        self.models = [model] + [m for m in FALLBACK_MODELS if m != model]

        with open(DATA_DIR / "embed.json", encoding="utf-8") as f:
            self.global_embed_config = json.load(f)

        LOGGER.info(f"AI Cog initialized: primary={model}, fallbacks={len(self.models) - 1}")

    @app_commands.command(name="ai", description="AI 問答")
    @app_commands.describe(question="你的問題")
    async def ai_command(self, interaction: discord.Interaction, question: str) -> None:
        """Ask AI a question.

        Args:
            interaction: Discord interaction
            question: User's question to the AI
        """
        if not question or not question.strip():
            await interaction.response.send_message("請提供問題內容", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            LOGGER.debug(f"AI request: user={interaction.user.name}, question={question[:100]}")

            messages: list[ChatCompletionMessageParam] = [
                {
                    "role": "system",
                    "content": """你是 Discord 聊天機器人。

                    規則：
                    - 語言：繁體中文
                    - 長度：簡潔回答，100-300字為主，最多500字
                    - 格式：使用純文字，不要使用 Markdown 語法（如 #、**、- 等）
                    - 列表：使用數字編號或簡單換行，不使用符號
                    - 語氣：友善、有幫助
                    - 直接回答問題，不要輸出思考過程

                    禁止內容：
                    - 仇恨言論、歧視（種族/性別/宗教/性取向）
                    - 暴力、威脅、騷擾
                    - 成人/性相關內容
                    - 非法活動

                    遇到不當問題請禮貌拒絕。提供正面、安全的回應。
                    """,
                },
                {"role": "user", "content": question},
            ]

            response = ""
            last_error: Exception | None = None

            for model in self.models:
                try:
                    completion = await self.client.chat.completions.create(
                        model=model,
                        max_tokens=800,
                        messages=messages,
                    )

                    if not completion.choices:
                        LOGGER.warning(f"AI [{model}]: no choices, trying next model")
                        continue

                    raw = completion.choices[0].message.content or ""
                    response = re.sub(r"<think>[\s\S]*?</think>", "", raw)
                    response = re.sub(r"<think>[\s\S]*$", "", response)
                    response = response.strip()

                    LOGGER.info(f"AI [{model}]: raw={len(raw)}, clean={len(response)}")
                    if response:
                        break
                except RateLimitError as e:
                    LOGGER.warning(f"AI rate limit on {model}, trying next model")
                    last_error = e
                    continue
                except APITimeoutError:
                    LOGGER.warning(f"AI [{model}] timed out, trying next model")
                    continue

            if response:
                embed = discord.Embed(
                    title="AI 回應",
                    color=discord.Color.blue(),
                )

                global_author = self.global_embed_config.get("author", {})
                if global_author.get("name"):
                    embed.set_author(
                        name=global_author.get("name"),
                        icon_url=global_author.get("icon_url"),
                        url=global_author.get("url"),
                    )

                embed.set_thumbnail(url=interaction.user.display_avatar.url)

                question_display = question
                if len(question) > 1020:
                    question_display = question[:1017] + "..."
                embed.add_field(name="**提問**", value=f"> {question_display}", inline=False)

                if len(response) > 1020:
                    response = response[:1017] + "..."
                embed.add_field(name="**回應**", value=response, inline=False)
                await interaction.followup.send(embed=embed)
            elif last_error:
                raise last_error
            else:
                LOGGER.warning("Empty content after all models")
                await interaction.followup.send("AI 回應為空，請重試")

        except RateLimitError as e:
            await interaction.followup.send("AI 功能目前使用人數過多，請稍後再試")
            LOGGER.error(f"AI command error: {e}")
        except PermissionDeniedError as e:
            await interaction.followup.send("AI 服務暫時無法使用，請聯絡管理員")
            LOGGER.error(f"AI command error: {e}")
        except AuthenticationError as e:
            await interaction.followup.send("AI 服務設定異常，請聯絡管理員")
            LOGGER.error(f"AI command error: {e}")
        except APITimeoutError as e:
            await interaction.followup.send("AI 回應逾時，請稍後再試")
            LOGGER.error(f"AI command error: {e}")
        except (BadRequestError, Exception) as e:
            await interaction.followup.send("AI 服務暫時無法使用，請稍後再試")
            LOGGER.error(f"AI command error: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AI(bot))
