"""Logging configuration"""

import logging
import os
import sys

try:
    from rich.console import Console
    from rich.logging import RichHandler

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class _ModuleFormatter(logging.Formatter):
    """Colour-coded module tag prefix for Rich logging.

    First-party loggers (our code) → cyan
    Third-party / built-in         → dim
    """

    _OWN_PREFIXES = ("cogs.", "core.", "discord_bot", "shared.")

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


def setup_logging() -> None:
    """Configure application logging with Rich handler"""
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)

    if RICH_AVAILABLE:
        try:
            # Enable UTF-8 output on Windows
            if sys.platform == "win32":
                import codecs

                sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer)
                sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer)

            console = Console(
                force_terminal=True,
                width=120,
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

            rich_handler.setFormatter(
                _ModuleFormatter(
                    fmt="%(module_tag)s │ %(message)s",
                    datefmt="[%Y-%m-%d %H:%M:%S]",
                )
            )

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

    webhook_url = os.getenv("ERROR_WEBHOOK_URL", "")
    if webhook_url:
        from pathlib import Path

        _backend = str(Path(__file__).resolve().parent.parent.parent)
        if _backend not in sys.path:
            sys.path.insert(0, _backend)

        from shared.discord_webhook_handler import DiscordWebhookHandler

        logging.getLogger().addHandler(DiscordWebhookHandler(webhook_url, service_name="discord"))

    # Reduce third-party log noise
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
