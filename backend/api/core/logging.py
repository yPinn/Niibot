"""API logging configuration."""

import logging

from core.config import Settings
from shared.logging_setup import setup_logging as _setup_logging

_SUPPRESS: dict[str, int] = {
    "uvicorn.access": logging.WARNING,
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
}

_OWN_PREFIXES = ("core.", "services.", "routers.", "shared.")


def setup_logging(settings: Settings) -> None:
    _setup_logging(
        log_level=settings.log_level,
        webhook_url=settings.error_webhook_url if settings.is_production else "",
        service_name="api",
        suppress_loggers=_SUPPRESS,
        own_prefixes=_OWN_PREFIXES,
        console=settings.is_development,
    )
    logging.getLogger(__name__).info(f"Logging: {settings.log_level} | Env: {settings.environment}")
