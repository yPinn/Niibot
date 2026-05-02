"""Discord bot health check server."""

import logging
from typing import TYPE_CHECKING, Any

from shared.ai_provider import get_primary_model_label
from shared.health_server_base import BaseHealthServer

from .config import get_settings

if TYPE_CHECKING:
    from discord.ext.commands import Bot

LOGGER: logging.Logger = logging.getLogger(__name__)


class HealthCheckServer(BaseHealthServer):
    """Discord-specific health check server."""

    SERVICE_NAME = "niibot-discord"

    def __init__(
        self, bot: "Bot | None" = None, host: str = "0.0.0.0", port: int | None = None
    ) -> None:
        self.bot: Any = bot
        super().__init__(host=host, port=port or get_settings().port)

    async def get_ready(self) -> bool:
        return self.bot is not None and self.bot.is_ready()

    async def get_metrics(self) -> dict:
        ready = await self.get_ready()
        ws_latency_ms = round(self.bot.latency * 1000) if ready else None
        s = get_settings()
        return {
            "bot_id": str(self.bot.user.id) if ready and self.bot.user else None,
            "guilds": len(self.bot.guilds) if ready else 0,
            "cogs": len(self.bot.cogs) if ready else 0,
            "ws_latency_ms": ws_latency_ms,
            "ai_model": get_primary_model_label(
                groq_api_key=s.groq_api_key,
                groq_model=s.groq_model,
                gemini_api_key=s.gemini_api_key,
                gemini_model=s.gemini_model,
                openrouter_api_key=s.openrouter_api_key,
                openrouter_model=s.openrouter_model,
                provider_order=("gemini", "groq", "openrouter"),
            ),
        }
