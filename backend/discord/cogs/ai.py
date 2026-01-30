"""AI chat commands using OpenRouter API"""

import json
import logging
import os

from config import DATA_DIR
from discord.ext import commands
from openai import OpenAI

import discord
from discord import app_commands

LOGGER = logging.getLogger("AI")


class AI(commands.Cog):
    REASONING_MODELS = ["glm-4.5-air", "deepseek-r1t2-chimera"]

    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
        self.is_reasoning = any(rm in model for rm in self.REASONING_MODELS)
        self.max_tokens = 500 if self.is_reasoning else 300

        with open(DATA_DIR / "embed.json", encoding="utf-8") as f:
            self.global_embed_config = json.load(f)

        LOGGER.info(
            f"AI Cog initialized: model={model}, "
            f"reasoning={self.is_reasoning}, max_tokens={self.max_tokens}"
        )

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

            completion = self.client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[
                    {
                        "role": "system",
                        "content": """你是 Discord 聊天機器人。

                        規則：
                        - 語言：繁體中文
                        - 長度：簡潔回答，100-300字為主，最多500字
                        - 格式：使用純文字，不要使用 Markdown 語法（如 #、**、- 等）
                        - 列表：使用數字編號或簡單換行，不使用符號
                        - 語氣：友善、有幫助

                        禁止內容：
                        - 仇恨言論、歧視（種族/性別/宗教/性取向）
                        - 暴力、威脅、騷擾
                        - 成人/性相關內容
                        - 非法活動

                        遇到不當問題請禮貌拒絕。提供正面、安全的回應。
                        """,
                    },
                    {"role": "user", "content": question},
                ],
            )

            if not completion.choices:
                LOGGER.error("No choices in API response")
                await interaction.followup.send("AI 回應格式錯誤，請稍後再試")
                return

            msg = completion.choices[0].message
            response = msg.content or ""

            if not response and hasattr(msg, "reasoning") and msg.reasoning:
                response = msg.reasoning
                LOGGER.debug("Using reasoning field")

            LOGGER.debug(f"Response length: {len(response)}")

            if response:
                embed = discord.Embed(
                    title="ChatGPT",
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
            else:
                LOGGER.warning("Empty content from API")
                await interaction.followup.send("AI 回應為空，請重試")

        except Exception as e:
            error_msg = str(e)
            if "rate limit" in error_msg.lower() or "429" in error_msg:
                await interaction.followup.send("API 請求過於頻繁，請稍後再試")
            elif "timeout" in error_msg.lower():
                await interaction.followup.send("請求超時，請稍後再試")
            elif "authentication" in error_msg.lower() or "401" in error_msg:
                await interaction.followup.send("API 認證失敗")
            elif "400" in error_msg:
                await interaction.followup.send("請求格式錯誤，請稍後再試")
            else:
                await interaction.followup.send("AI 服務暫時無法使用，請稍後再試")
            LOGGER.error(f"AI command error: {error_msg}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AI(bot))
