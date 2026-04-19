"""AI chat commands using OpenRouter API"""

import asyncio
import json
import logging
import re
import time

import discord
from discord import app_commands
from discord.ext import commands
from openai import (
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam

from core import DATA_DIR, EmbedFactory, get_settings, load_json

LOGGER = logging.getLogger(__name__)

_FREE_MODELS_PATH = DATA_DIR / "free_models.json"

_HARDCODED_FALLBACKS: list[str] = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "openai/gpt-oss-120b:free",
    "z-ai/glm-4.5-air:free",
]


def _load_fallback_models(primary: str) -> list[str]:
    """Load enabled fallback models from shared/free_models.json, excluding primary."""
    if _FREE_MODELS_PATH.exists():
        try:
            with open(_FREE_MODELS_PATH) as f:
                data = json.load(f)
            models = [m["id"] for m in data.get("models", []) if m.get("enabled", False)]
            LOGGER.info(f"Loaded {len(models)} fallback models from {_FREE_MODELS_PATH.name}")
        except Exception as e:
            LOGGER.warning(f"Failed to load free_models.json: {e}, using hardcoded fallbacks")
            models = list(_HARDCODED_FALLBACKS)
    else:
        LOGGER.warning(f"{_FREE_MODELS_PATH.name} not found, using hardcoded fallbacks")
        models = list(_HARDCODED_FALLBACKS)

    return [m for m in models if m != primary]


_SYSTEM_PROMPT = (
    "你是 Discord 聊天機器人。\n\n"
    "規則：\n"
    "- 語言：繁體中文，嚴禁使用簡體中文（除非使用者明確要求）\n"
    "- 長度：簡潔回答，100-300字為主，最多500字\n"
    "- 格式：多個概念或步驟請用換行分段，保持易讀；禁止使用標題（#）\n"
    "- 列表：可使用數字編號或「-」條列，但不要過度使用\n"
    "- 語氣：友善、有幫助\n"
    "- 直接回答問題，不要輸出思考過程\n\n"
    "禁止內容：\n"
    "- 仇恨言論、歧視（種族/性別/宗教/性取向）\n"
    "- 暴力、威脅、騷擾\n"
    "- 成人/性相關內容\n"
    "- 非法活動\n\n"
    "遇到不當問題請禮貌拒絕。提供正面、安全的回應。"
)


class AICog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        s = get_settings()
        api_key = s.openrouter_api_key
        model = s.openrouter_model

        if not api_key or api_key.strip() == "":
            raise ValueError("OPENROUTER_API_KEY is required but not set in .env file")

        if not model or model.strip() == "":
            raise ValueError("OPENROUTER_MODEL is required but not set in .env file")

        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=45.0,
        )
        self.models = [model] + _load_fallback_models(model)

        self._embed = EmbedFactory(load_json(DATA_DIR / "embed.json"))

    async def cog_load(self) -> None:
        LOGGER.info(f"AI ready: primary={self.models[0]}, fallbacks={len(self.models) - 1}")

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
            LOGGER.info(f"AI request: user={interaction.user.name}, question={question[:100]}")

            messages: list[ChatCompletionMessageParam] = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ]

            response = ""
            last_error: Exception | None = None
            t_start = time.monotonic()

            for model in self.models:
                try:
                    completion = await asyncio.wait_for(
                        self.client.chat.completions.create(
                            model=model,
                            max_tokens=800,
                            messages=messages,
                            # Prevent reasoning models (e.g. DeepSeek R1) from
                            # consuming the max_tokens budget on <think> content.
                            extra_body={"include_reasoning": False},
                        ),
                        timeout=40.0,
                    )

                    if not completion.choices:
                        LOGGER.warning(f"AI [{model}]: no choices, trying next model")
                        continue

                    raw = completion.choices[0].message.content or ""
                    response = re.sub(r"<think>[\s\S]*?</think>", "", raw)
                    response = re.sub(r"<think>[\s\S]*$", "", response)
                    response = response.strip()

                    elapsed = time.monotonic() - t_start
                    LOGGER.info(
                        f"AI [{model}]: {elapsed:.1f}s, raw={len(raw)}, clean={len(response)}"
                    )
                    if response:
                        break
                except TimeoutError:
                    LOGGER.warning(f"AI [{model}] timed out (40s), trying next model")
                    continue
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
    await bot.add_cog(AICog(bot))
