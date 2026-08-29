"""Core modules for Twitch bot."""

from .config import (
    BOT_SCOPES,
    BROADCASTER_SCOPES,
    COMPONENTS_DIR,
    DATA_DIR,
    TWITCH_DIR,
    get_settings,
)
from .eventsub_catalog import get_channel_subscriptions
from .guards import check_command, has_role, is_on_cooldown, record_cooldown
from .health_server import HealthCheckServer
from .logging_setup import setup_logging
from .pg_listener import pg_listen

__all__ = [
    # Settings
    "get_settings",
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
