"""Core modules for Twitch bot."""

from .config import (
    BOT_SCOPES,
    BROADCASTER_SCOPES,
    COMPONENTS_DIR,
    DATA_DIR,
    TWITCH_DIR,
    get_settings,
    load_env_config,
    validate_env_vars,
)
from .guards import check_command, has_role, is_on_cooldown, record_cooldown
from .health_server import HealthCheckServer
from .logging import setup_logging
from .pg_listener import pg_listen
from .subscriptions import get_channel_subscriptions

__all__ = [
    # Settings
    "get_settings",
    "validate_env_vars",
    "load_env_config",
    # Path Constants
    "TWITCH_DIR",
    "COMPONENTS_DIR",
    "DATA_DIR",
    # Scope Constants
    "BOT_SCOPES",
    "BROADCASTER_SCOPES",
    # Setup functions
    "setup_logging",
    # Services
    "HealthCheckServer",
    # Twitch specific
    "get_channel_subscriptions",
    # Guards
    "check_command",
    "has_role",
    "is_on_cooldown",
    "record_cooldown",
    # PG Listener
    "pg_listen",
]
