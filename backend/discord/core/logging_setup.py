"""Discord bot logging configuration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from shared.logging_setup import setup_logging as _setup_logging

if TYPE_CHECKING:
    from core.config import DiscordBotSettings

_SUPPRESS: dict[str, int] = {
    "discord": logging.WARNING,
    "discord.http": logging.WARNING,
    "aiohttp": logging.WARNING,
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
}

_OWN_PREFIXES = ("cogs.", "core.", "shared.")


def setup_logging(settings: DiscordBotSettings) -> None:
    _setup_logging(
        log_level=settings.log_level,
        webhook_url=settings.error_webhook_url if settings.is_production else "",
        service_name="discord",
        suppress_loggers=_SUPPRESS,
        own_prefixes=_OWN_PREFIXES,
        skip_suffixes=("cog", "__init__"),
        console=settings.is_development,
    )
