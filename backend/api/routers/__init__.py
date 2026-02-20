"""API Routers"""

from . import (
    analytics_router,
    auth_router,
    bots_router,
    channels_router,
    commands_router,
    events_router,
    game_queue_router,
    message_triggers_router,
    stats_router,
    timers_router,
)

__all__ = [
    "auth_router",
    "channels_router",
    "analytics_router",
    "commands_router",
    "events_router",
    "game_queue_router",
    "message_triggers_router",
    "stats_router",
    "timers_router",
    "bots_router",
]
