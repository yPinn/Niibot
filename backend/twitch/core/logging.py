import logging
import os

try:
    from rich.console import Console
    from rich.logging import RichHandler

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


def setup_logging() -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level, logging.INFO)

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

            logging.basicConfig(
                level=level,
                format="%(message)s",
                datefmt="[%Y-%m-%d %H:%M:%S]",
                handlers=[rich_handler],
                force=True,
            )
            logger = logging.getLogger("Bot")
            logger.info("[bold green]✓[/bold green] Rich logging enabled", extra={"markup": True})
        except Exception as e:
            logging.basicConfig(
                level=level,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            logger = logging.getLogger("Bot")
            logger.warning(f"Failed to setup Rich logging: {e}, using standard logging")
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        logger = logging.getLogger("Bot")
        logger.info("Standard logging enabled (install 'rich' for better output)")

    if level == logging.DEBUG:
        logging.getLogger("twitchio").setLevel(logging.DEBUG)
        logging.getLogger("twitchio.eventsub").setLevel(logging.DEBUG)
        logging.getLogger("twitchio.http").setLevel(logging.DEBUG)
        logging.getLogger("twitchio.websockets").setLevel(logging.DEBUG)
        logging.getLogger("httpx").setLevel(logging.INFO)
    else:
        logging.getLogger("twitchio").setLevel(logging.INFO)
        logging.getLogger("twitchio.eventsub").setLevel(logging.INFO)
        logging.getLogger("twitchio.http").setLevel(logging.WARNING)
        logging.getLogger("twitchio.websockets").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)

    logging.getLogger("asyncio").setLevel(logging.ERROR)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
