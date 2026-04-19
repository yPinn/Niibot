"""Discord bot logging configuration."""

import logging
import os

from shared.logging_setup import setup_logging as _setup_logging

# Discord-specific logger suppression
_SUPPRESS: dict[str, int] = {
    "discord": logging.WARNING,
    "discord.http": logging.WARNING,
    "aiohttp": logging.WARNING,
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
}


class _ModuleFormatter(logging.Formatter):
    """Colour-coded module tag prefix for Rich logging.

    First-party loggers (our code) → cyan
    Third-party / built-in         → dim
    """

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


def setup_logging() -> None:
    _setup_logging(
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        webhook_url=os.getenv("ERROR_WEBHOOK_URL", ""),
        service_name="discord",
        suppress_loggers=_SUPPRESS,
        formatter_factory=_make_formatter,
    )
