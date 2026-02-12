"""Core modules for Discord bot."""

from .config import BACKEND_DIR, BOT_NAME, BOT_VERSION, COGS_DIR, DATA_DIR, DISCORD_DIR, BotConfig
from .health_server import HealthCheckServer
from .logging import setup_logging
from .rate_limiter import RateLimitMonitor, RateLimitStats

__all__ = [
    # Config
    "BotConfig",
    "BOT_NAME",
    "BOT_VERSION",
    # Paths
    "DISCORD_DIR",
    "BACKEND_DIR",
    "COGS_DIR",
    "DATA_DIR",
    # Services
    "HealthCheckServer",
    "RateLimitMonitor",
    "RateLimitStats",
    # Logging
    "setup_logging",
]
