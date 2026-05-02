"""AI chat commands using multi-provider LLM routing."""

import logging

import discord
from discord import app_commands
from discord.ext import commands
from openai import (
    APITimeoutError,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam

from core import DATA_DIR, EmbedFactory, get_settings, load_json
from shared.ai_provider import ProviderEntry, build_provider_chain, call_provider_chain

LOGGER: logging.Logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "你是 Discord 聊天機器人，回應會公開顯示於伺服器頻道，須符合 Discord 服務條款。\n\n"
    "格式：\n"
    "- 語言：繁體中文（除非使用者明確要求其他語言）\n"
    "- 長度：100-300字為主，最多500字\n"
    "- 多個概念或步驟請換行分段；禁止使用標題（#）\n"
    "- 列表：可使用數字編號或「-」條列，不要過度使用\n"
    "- 語氣：友善、有幫助\n"
    "- 直接回答，不輸出思考過程\n\n"
    "平台限制：禁止生成仇恨攻擊、性相關、或針對特定人的騷擾威脅等內容；"
    "遇此類請求請用冷幽默方式婉拒（例如假裝系統錯誤、自稱腦袋當機、或用無辜語氣說做不到），"
    "不要直接說「我無法回答」。知識、創作、娛樂等一般問題請正常回答。"
)


class AICog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        s = get_settings()
        self.provider_chain: list[ProviderEntry] = build_provider_chain(
            groq_api_key=s.groq_api_key,
            groq_model=s.groq_model,
            gemini_api_key=s.gemini_api_key,
            gemini_model=s.gemini_model,
            openrouter_api_key=s.openrouter_api_key,
            openrouter_model=s.openrouter_model,
            data_dir=DATA_DIR,
            timeout=40.0,
            provider_order=("gemini", "groq", "openrouter"),  # quality-first for rich responses
        )
        self._embed = EmbedFactory(load_json(DATA_DIR / "embed.json"))

    async def cog_load(self) -> None:
        LOGGER.info(f"AI ready: {len(self.provider_chain)} provider entries")

    @app_commands.command(name="ai", description="AI 問答")
    @app_commands.describe(question="你的問題")
    async def ai_command(self, interaction: discord.Interaction, question: str) -> None:
        if not question or not question.strip():
            await interaction.response.send_message("請提供問題內容", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            LOGGER.info(f"AI request: user={interaction.user.name}, question={question[:100]}")

            messages: list[ChatCompletionMessageParam] = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ]

            response, last_error = await call_provider_chain(
                self.provider_chain, messages, max_tokens=800
            )

            if response:
                embed = self._embed.build(
                    title="AI 回應",
                    color=discord.Color.blue(),
                    thumbnail=interaction.user.display_avatar.url,
                )

                question_display = question if len(question) <= 1020 else question[:1017] + "..."
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
            LOGGER.warning(f"[{interaction.user.name}] AI rate limit: {e}")
        except PermissionDeniedError as e:
            await interaction.followup.send("AI 服務暫時無法使用，請聯絡管理員")
            LOGGER.error(f"[{interaction.user.name}] AI permission denied: {e}")
        except AuthenticationError as e:
            await interaction.followup.send("AI 服務設定異常，請聯絡管理員")
            LOGGER.error(f"[{interaction.user.name}] AI authentication error: {e}")
        except APITimeoutError as e:
            await interaction.followup.send("AI 回應逾時，請稍後再試")
            LOGGER.warning(f"[{interaction.user.name}] AI timeout: {e}")
        except Exception as e:
            await interaction.followup.send("AI 服務暫時無法使用，請稍後再試")
            LOGGER.error(f"[{interaction.user.name}] AI unexpected error ({type(e).__name__}): {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AICog(bot))
