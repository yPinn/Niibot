"""Core modules for Twitch bot."""

from .config import (
    BOT_SCOPES,
    BROADCASTER_SCOPES,
    DATA_DIR,
    get_settings,
    load_env_config,
    validate_env_vars,
)
from .database import setup_database_schema
from .logging import setup_logging
from .subscriptions import get_channel_subscriptions

__all__ = [
    # Settings
    "get_settings",
    "validate_env_vars",
    "load_env_config",
    # Constants
    "BOT_SCOPES",
    "BROADCASTER_SCOPES",
    "DATA_DIR",
    # Setup functions
    "setup_logging",
    "setup_database_schema",
    # Twitch specific
    "get_channel_subscriptions",
]
