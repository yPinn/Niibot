"""Logging configuration"""

import logging

from core.config import Settings

try:
    from rich.console import Console
    from rich.logging import RichHandler

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


def setup_logging(settings: Settings) -> None:
    """Configure application logging with Rich handler"""

    level = getattr(logging, settings.log_level, logging.INFO)

    if RICH_AVAILABLE:
        try:
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

            # force=True: override root logger pre-configured by uvicorn
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

    # Reduce third-party log noise
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    if settings.error_webhook_url:
        from shared.discord_webhook_handler import DiscordWebhookHandler

        logging.getLogger().addHandler(
            DiscordWebhookHandler(settings.error_webhook_url, service_name="api")
        )

    logger = logging.getLogger(__name__)
    logger.info(f"Logging: {settings.log_level} | Env: {settings.environment}")
