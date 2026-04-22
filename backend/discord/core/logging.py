"""Discord bot logging configuration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from shared.logging_setup import setup_logging as _setup_logging

if TYPE_CHECKING:
    from core.config import DiscordBotSettings

# Discord-specific logger suppression
_SUPPRESS: dict[str, int] = {
    "discord": logging.WARNING,
    "discord.http": logging.WARNING,
    "aiohttp": logging.WARNING,
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
}


class _ModuleFormatter(logging.Formatter):
    """Colour-coded prefix: first-party loggers → cyan, third-party → dim."""

    _OWN_PREFIXES = ("cogs.", "core.", "discord.", "shared.")

    def _module_tag(self, record: logging.LogRecord) -> str:
        parts = record.name.split(".")
        name = parts[-2] if parts[-1] == "cog" and len(parts) >= 2 else parts[-1]
        padded = f"{name:<16}"
        if any(record.name.startswith(p) for p in self._OWN_PREFIXES):
            return f"[cyan]{padded}[/cyan]"
        return f"[dim]{padded}[/dim]"

    def format(self, record: logging.LogRecord) -> str:
        record.module_tag = self._module_tag(record)
        return super().format(record)


def _make_formatter() -> logging.Formatter:
    return _ModuleFormatter(
        fmt="%(module_tag)s │ %(message)s",
        datefmt="[%Y-%m-%d %H:%M:%S]",
    )


def setup_logging(settings: DiscordBotSettings) -> None:
    _setup_logging(
        log_level=settings.log_level,
        webhook_url=settings.error_webhook_url,
        service_name="discord",
        suppress_loggers=_SUPPRESS,
        formatter_factory=_make_formatter,
    )
