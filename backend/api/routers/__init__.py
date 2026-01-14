"""API Routers"""

from . import (
    analytics_router,
    auth_router,
    bots_router,
    channels_router,
    commands_router,
    stats_router,
)

__all__ = [
    "auth_router",
    "channels_router",
    "analytics_router",
    "commands_router",
    "stats_router",
    "bots_router",
]
