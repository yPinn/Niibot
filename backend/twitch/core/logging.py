"""Twitch bot logging configuration."""

import logging
import os

from shared.logging_setup import setup_logging as _setup_logging


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


def setup_logging() -> None:
    log_level_str = os.getenv("LOG_LEVEL", "INFO")
    level = getattr(logging, log_level_str.upper(), logging.INFO)
    _setup_logging(
        log_level=log_level_str,
        webhook_url=os.getenv("ERROR_WEBHOOK_URL", ""),
        service_name="twitch",
        suppress_loggers=_build_suppress(level),
    )
