"""API logging configuration."""

import logging

from core.config import Settings
from shared.logging_setup import setup_logging as _setup_logging

_SUPPRESS: dict[str, int] = {
    "uvicorn.access": logging.WARNING,
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
}


def setup_logging(settings: Settings) -> None:
    _setup_logging(
        log_level=settings.log_level,
        webhook_url=settings.error_webhook_url or "",
        service_name="api",
        suppress_loggers=_SUPPRESS,
    )
    logging.getLogger(__name__).info(f"Logging: {settings.log_level} | Env: {settings.environment}")
