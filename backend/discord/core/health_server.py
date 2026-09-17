"""Discord bot health check server."""

import logging
import math
from typing import TYPE_CHECKING, Any

from shared.assistant.health import primary_model_label
from shared.health_server_base import BaseHealthServer

from .config import get_settings

if TYPE_CHECKING:
    from discord.ext.commands import Bot

LOGGER: logging.Logger = logging.getLogger(__name__)


class HealthCheckServer(BaseHealthServer):
    """Discord-specific health check server."""

    SERVICE_NAME = "nb-discord"

    def __init__(
        self, bot: "Bot | None" = None, host: str = "0.0.0.0", port: int | None = None
    ) -> None:
        self.bot: Any = bot
        super().__init__(host=host, port=port or get_settings().port)

    async def get_ready(self) -> bool:
        return self.bot is not None and self.bot.is_ready()

    def _get_ai_status(self) -> dict[str, object] | None:
        if self.bot is None:
            return None

        get_cog = getattr(self.bot, "get_cog", None)
        if not callable(get_cog):
            return None
        cog = get_cog("AICog")
        ai_health = getattr(cog, "ai_health", None)
        if not callable(ai_health):
            return None

        try:
            status = ai_health()
        except Exception:
            LOGGER.exception("Failed to collect Discord AI health")
            return None
        return status if isinstance(status, dict) else None

    async def get_metrics(self) -> dict:
        ready = await self.get_ready()
        latency = self.bot.latency * 1000 if ready else float("nan")
        ws_latency_ms = round(latency) if math.isfinite(latency) else None
        ai_status = self._get_ai_status()
        return {
            "bot_id": str(self.bot.user.id) if ready and self.bot.user else None,
            "guilds": len(self.bot.guilds) if ready else 0,
            "cogs": len(self.bot.cogs) if ready else 0,
            "ws_latency_ms": ws_latency_ms,
            "ai_model": primary_model_label(ai_status),
            "ai_status": ai_status,
        }
