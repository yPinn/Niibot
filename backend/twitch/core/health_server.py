"""Twitch bot health check server."""

import logging
from typing import TYPE_CHECKING, Any

from shared.ai_provider import get_primary_model_label
from shared.gauges import collect_runtime_gauges
from shared.health_server_base import BaseHealthServer

from .config import get_settings

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER: logging.Logger = logging.getLogger(__name__)


class HealthCheckServer(BaseHealthServer):
    """Twitch-specific health check server."""

    SERVICE_NAME = "nb-twitch"

    def __init__(self, bot: "Bot | None" = None, host: str = "0.0.0.0", port: int | None = None):
        self.bot: Any = bot
        super().__init__(host=host, port=port or get_settings().port)

    async def get_ready(self) -> bool:
        return self.bot is not None and self.bot.bot_id is not None

    async def get_metrics(self) -> dict:
        s = get_settings()
        gauges: dict = {"db_pool": None, "caches": {}}
        memory: dict[str, int] = {}
        if self.bot is not None:
            gauges = collect_runtime_gauges(self.bot._db_manager)
            memory = self.bot.memory_gauges()
        return {
            "bot_id": self.bot.bot_id if self.bot else None,
            "connected_channels": len(self.bot.subs.subscribed) if self.bot else 0,
            "components": len(self.bot._components) if self.bot else 0,
            "memory": memory,
            **gauges,
            "ai_model": get_primary_model_label(
                groq_api_key=s.groq_api_key,
                groq_model=s.groq_model,
                gemini_api_key=s.gemini_api_key,
                gemini_model=s.gemini_model,
                openrouter_api_key=s.openrouter_api_key,
                openrouter_model=s.openrouter_model,
                provider_order=("groq", "gemini", "openrouter"),
            ),
        }
