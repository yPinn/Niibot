"""Logging configuration"""

import logging

from rich.console import Console
from rich.logging import RichHandler

from core.config import Settings


def setup_logging(settings: Settings) -> None:
    """Configure application logging with Rich handler"""

    level = getattr(logging, settings.log_level, logging.INFO)

    # Configure Rich console
    console = Console(
        force_terminal=True,
        width=120,
        stderr=True,
    )

    # Configure Rich handler
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_level=True,
        show_path=False,
        markup=True,
        rich_tracebacks=True,
        tracebacks_show_locals=settings.is_development,
    )

    rich_handler.setFormatter(
        logging.Formatter(
            fmt="%(message)s",
            datefmt="[%Y-%m-%d %H:%M:%S]",
        )
    )

    # Configure root logger
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%Y-%m-%d %H:%M:%S]",
        handlers=[rich_handler],
        force=True,
    )

    # Reduce noise from uvicorn access logs
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # Log startup info
    logger = logging.getLogger(__name__)
    logger.info(f"Logging: {settings.log_level} | Env: {settings.environment}")
