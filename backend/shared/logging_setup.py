"""Shared logging setup for all Niibot services."""

from __future__ import annotations

import logging
import sys

try:
    from rich.console import Console
    from rich.logging import RichHandler

    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False

_FALLBACK_FORMAT = "%(asctime)s [%(name)s] %(levelname)s %(message)s"
_FALLBACK_DATEFMT = "%Y-%m-%d %H:%M:%S"


class _ModuleFormatter(logging.Formatter):
    """Show a padded module name before the message.

    Loggers whose name starts with an ``own_prefixes`` entry are highlighted
    in cyan; all others are dim (typically third-party libraries).
    ``skip_suffixes`` lists module-name segments that are uninformative (e.g.
    ``"cog"`` or ``"__init__"``), causing the parent segment to be used instead.
    """

    def __init__(
        self,
        fmt: str,
        datefmt: str,
        own_prefixes: tuple[str, ...] = (),
        skip_suffixes: tuple[str, ...] = ("__init__",),
    ) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        self._own_prefixes = own_prefixes
        self._skip_suffixes = skip_suffixes

    def _module_tag(self, record: logging.LogRecord) -> str:
        parts = record.name.split(".")
        name = parts[-1]
        if name in self._skip_suffixes and len(parts) >= 2:
            name = parts[-2]
        padded = f"{name:<16}"
        if self._own_prefixes and any(record.name.startswith(p) for p in self._own_prefixes):
            return f"[cyan]{padded}[/cyan]"
        return f"[dim]{padded}[/dim]"

    def format(self, record: logging.LogRecord) -> str:
        record.module_tag = self._module_tag(record)  # type: ignore[attr-defined]
        # Escape '[' so Rich (markup=True) does not consume [channel_name] prefixes as markup tags.
        record.msg = record.getMessage().replace("[", "\\[")
        record.args = None
        return super().format(record)


def setup_logging(
    log_level: str = "INFO",
    webhook_url: str = "",
    service_name: str = "niibot",
    suppress_loggers: dict[str, int] | None = None,
    own_prefixes: tuple[str, ...] = (),
    skip_suffixes: tuple[str, ...] = ("__init__",),
) -> None:
    """Configure application logging with Rich handler.

    Args:
        log_level: Log level string (e.g. ``"INFO"``, ``"DEBUG"``).
        webhook_url: Discord webhook URL for ERROR+ alerts. Empty = disabled.
        service_name: Used in webhook payloads (``"api"``, ``"discord"``, ``"twitch"``).
        suppress_loggers: Mapping of logger name → level to apply noise reduction.
        own_prefixes: Logger name prefixes treated as first-party (shown in cyan).
        skip_suffixes: Module name segments to skip when building the display tag
            (e.g. ``"cog"`` or ``"__init__"``).
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
            fmt = _ModuleFormatter(
                fmt="%(module_tag)s │ %(message)s",
                datefmt="[%Y-%m-%d %H:%M:%S]",
                own_prefixes=own_prefixes,
                skip_suffixes=skip_suffixes,
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
                format=_FALLBACK_FORMAT,
                datefmt=_FALLBACK_DATEFMT,
                force=True,
            )
            logging.getLogger(__name__).warning(
                f"Rich logging setup failed: {e}, using standard logging"
            )
    else:
        logging.basicConfig(
            level=level,
            format=_FALLBACK_FORMAT,
            datefmt=_FALLBACK_DATEFMT,
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
