"""Twitch bot health check server."""

import logging
from typing import TYPE_CHECKING, Any

from shared.health_server_base import BaseHealthServer

from .config import get_settings

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER: logging.Logger = logging.getLogger(__name__)


class HealthCheckServer(BaseHealthServer):
    """Twitch-specific health check server."""

    SERVICE_NAME = "niibot-twitch"

    def __init__(self, bot: "Bot | None" = None, host: str = "0.0.0.0", port: int | None = None):
        self.bot: Any = bot
        super().__init__(host=host, port=port or get_settings().port)

    async def get_ready(self) -> bool:
        return self.bot is not None and self.bot.bot_id is not None

    async def get_metrics(self) -> dict:
        return {
            "bot_id": self.bot.bot_id if self.bot else None,
            "connected_channels": len(self.bot._subscribed_channels) if self.bot else 0,
            "components": len(self.bot._components) if self.bot else 0,
        }
