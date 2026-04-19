"""Shared logging setup for all Niibot services."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable

try:
    from rich.console import Console
    from rich.logging import RichHandler

    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False


def setup_logging(
    log_level: str = "INFO",
    webhook_url: str = "",
    service_name: str = "niibot",
    suppress_loggers: dict[str, int] | None = None,
    formatter_factory: Callable[[], logging.Formatter] | None = None,
) -> None:
    """Configure application logging with Rich handler.

    Args:
        log_level: Log level string (e.g. ``"INFO"``, ``"DEBUG"``).
        webhook_url: Discord webhook URL for ERROR+ alerts. Empty = disabled.
        service_name: Used in webhook payloads (``"api"``, ``"discord"``, ``"twitch"``).
        suppress_loggers: Mapping of logger name → level to apply noise reduction.
        formatter_factory: Optional callable that returns a custom ``logging.Formatter``.
            If None, a standard message-only formatter is used with Rich.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    if _RICH_AVAILABLE:
        try:
            if sys.platform == "win32":
                import codecs

                if hasattr(sys.stdout, "buffer"):
                    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer)
                if hasattr(sys.stderr, "buffer"):
                    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer)

            console = Console(force_terminal=True, width=120)
            fmt = (
                formatter_factory()
                if formatter_factory
                else logging.Formatter(fmt="%(message)s", datefmt="[%Y-%m-%d %H:%M:%S]")
            )
            rich_handler = RichHandler(
                console=console,
                show_time=True,
                show_level=True,
                show_path=False,
                markup=True,
                rich_tracebacks=True,
                tracebacks_show_locals=False,
                tracebacks_width=120,
            )
            rich_handler.setFormatter(fmt)
            logging.basicConfig(level=level, handlers=[rich_handler], force=True)
        except Exception as e:
            logging.basicConfig(
                level=level,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
                force=True,
            )
            logging.getLogger(__name__).warning(
                f"Rich logging setup failed: {e}, using standard logging"
            )
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            force=True,
        )

    # Attach Discord webhook handler for ERROR+ alerts
    if webhook_url:
        from shared.discord_webhook_handler import DiscordWebhookHandler

        logging.getLogger().addHandler(
            DiscordWebhookHandler(webhook_url, service_name=service_name)
        )

    # Apply per-service logger suppression
    if suppress_loggers:
        for name, lvl in suppress_loggers.items():
            logging.getLogger(name).setLevel(lvl)
