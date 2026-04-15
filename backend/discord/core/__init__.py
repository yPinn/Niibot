"""Core modules for Discord bot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import (
    BACKEND_DIR,
    BOT_NAME,
    BOT_VERSION,
    COGS_DIR,
    DATA_DIR,
    DISCORD_DIR,
    GIT_COMMIT,
    BotConfig,
)
from .embed_factory import EmbedFactory
from .health_server import HealthCheckServer
from .logging import setup_logging
from .rate_limiter import RateLimitMonitor, RateLimitStats
from .views import UserBoundView


def load_json(path: Path, default: dict | list | None = None) -> Any:
    """Load a JSON file, returning *default* (empty dict) on any error."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


__all__ = [
    # Config
    "BotConfig",
    "BOT_NAME",
    "BOT_VERSION",
    "GIT_COMMIT",
    # Paths
    "DISCORD_DIR",
    "BACKEND_DIR",
    "COGS_DIR",
    "DATA_DIR",
    # Utilities
    "EmbedFactory",
    "UserBoundView",
    "load_json",
    # Services
    "HealthCheckServer",
    "RateLimitMonitor",
    "RateLimitStats",
    # Logging
    "setup_logging",
]
