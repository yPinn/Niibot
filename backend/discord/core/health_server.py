"""Discord bot health check server."""

import logging
from typing import TYPE_CHECKING, Any

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
        return {
            "bot_id": str(self.bot.user.id) if ready and self.bot.user else None,
            "guilds": len(self.bot.guilds) if ready else 0,
            "cogs": len(self.bot.cogs) if ready else 0,
            "ws_latency_ms": ws_latency_ms,
        }
