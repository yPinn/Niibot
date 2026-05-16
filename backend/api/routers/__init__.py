"""API Routers"""

from . import (
    admin_router,
    ai_settings_router,
    analytics_router,
    auth_router,
    bots_router,
    channels_router,
    commands_router,
    crosshairs_router,
    donation_router,
    events_router,
    game_queue_router,
    message_triggers_router,
    payment_config_router,
    stats_router,
    timers_router,
    video_queue_router,
)

__all__ = [
    "admin_router",
    "ai_settings_router",
    "auth_router",
    "channels_router",
    "analytics_router",
    "commands_router",
    "crosshairs_router",
    "donation_router",
    "events_router",
    "game_queue_router",
    "message_triggers_router",
    "payment_config_router",
    "stats_router",
    "timers_router",
    "bots_router",
    "video_queue_router",
]
