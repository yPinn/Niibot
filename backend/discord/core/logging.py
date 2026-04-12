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
                logging.Formatter(fmt="%(message)s", datefmt="[%Y-%m-%d %H:%M:%S]")
            )

            logging.basicConfig(
                level=level,
                format="%(message)s",
                datefmt="[%Y-%m-%d %H:%M:%S]",
                handlers=[rich_handler],
                force=True,
            )
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
