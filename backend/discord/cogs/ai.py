"""AI chat commands using OpenRouter API"""

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
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam

from core import DATA_DIR, EmbedFactory, get_settings, load_json

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
        api_key = s.openrouter_api_key
        model = s.openrouter_model

        if not api_key or api_key.strip() == "":
            raise ValueError("OPENROUTER_API_KEY is required but not set in .env file")

        if not model or model.strip() == "":
            raise ValueError("OPENROUTER_MODEL is required but not set in .env file")

        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=40.0,
        )
        self.models = [model] + _load_fallback_models(model)

        self._embed = EmbedFactory(load_json(DATA_DIR / "embed.json"))

    async def cog_load(self) -> None:
        LOGGER.info(f"AI ready: primary={self.models[0]}, fallbacks={len(self.models) - 1}")

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

            response = ""
            last_error: Exception | None = None
            t_start = time.monotonic()

            for model in self.models:
                try:
                    completion = await self.client.chat.completions.create(
                        model=model,
                        max_tokens=800,
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
