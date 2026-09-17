"""Twitch bot health check server."""

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from shared.assistant.health import primary_model_label
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

    def _get_ai_status(self) -> dict[str, object] | None:
        if self.bot is None:
            return None

        components = getattr(self.bot, "_components", None)
        if not isinstance(components, Mapping):
            return None

        for component in components.values():
            ai_health = getattr(component, "ai_health", None)
            if not callable(ai_health):
                continue
            try:
                status = ai_health()
            except Exception:
                LOGGER.exception("Failed to collect Twitch AI health")
                return None
            return status if isinstance(status, dict) else None
        return None

    async def get_metrics(self) -> dict:
        gauges: dict = {"db_pool": None, "caches": {}}
        memory: dict[str, int] = {}
        if self.bot is not None:
            gauges = collect_runtime_gauges(self.bot._db_manager)
            memory = self.bot.memory_gauges()
        ai_status = self._get_ai_status()
        return {
            "bot_id": self.bot.bot_id if self.bot else None,
            "connected_channels": len(self.bot.subs.subscribed) if self.bot else 0,
            "components": len(self.bot._components) if self.bot else 0,
            "memory": memory,
            **gauges,
            "ai_model": primary_model_label(ai_status),
            "ai_status": ai_status,
        }
