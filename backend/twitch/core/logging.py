"""Twitch bot logging configuration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from shared.logging_setup import setup_logging as _setup_logging

if TYPE_CHECKING:
    from core.config import TwitchBotSettings

_OWN_PREFIXES = ("core.", "components.", "utils.", "shared.")


def _build_suppress(level: int) -> dict[str, int]:
    """Build per-level suppression dict for twitchio loggers."""
    if level == logging.DEBUG:
        return {
            "twitchio": logging.DEBUG,
            "twitchio.eventsub": logging.DEBUG,
            "twitchio.http": logging.DEBUG,
            "twitchio.websockets": logging.DEBUG,
            "httpx": logging.INFO,
            "asyncio": logging.ERROR,
            "asyncpg": logging.WARNING,
            "openai": logging.WARNING,
            "aiohttp": logging.WARNING,
            "httpcore": logging.WARNING,
        }
    return {
        "twitchio": logging.INFO,
        "twitchio.eventsub": logging.INFO,
        "twitchio.http": logging.WARNING,
        "twitchio.websockets": logging.WARNING,
        "asyncio": logging.ERROR,
        "asyncpg": logging.WARNING,
        "openai": logging.WARNING,
        "aiohttp": logging.WARNING,
        "httpx": logging.WARNING,
        "httpcore": logging.WARNING,
    }


def setup_logging(settings: TwitchBotSettings) -> None:
    level = getattr(logging, settings.log_level, logging.INFO)
    _setup_logging(
        log_level=settings.log_level,
        webhook_url=settings.error_webhook_url if settings.is_production else "",
        service_name="twitch",
        suppress_loggers=_build_suppress(level),
        own_prefixes=_OWN_PREFIXES,
    )
