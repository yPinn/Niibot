"""Shared logging setup for all Niibot services.

All application code keeps using the stdlib ``logging`` API
(``logging.getLogger(__name__).info(...)``). structlog is wired in only as
the *formatter* on the root handler, so:

* third-party loggers (twitchio, discord.py, uvicorn, asyncpg) and our own
  loggers render through one pipeline;
* ``console`` mode gives a readable coloured line for local dev;
* otherwise every record is emitted as one JSON object per line, ready for
  the log viewer and for grepping by ``request_id`` / ``code``.

Structured fields travel via the stdlib ``extra={}`` kwarg (picked up by
``ExtraAdder``) and via ``structlog.contextvars`` bindings (merged by
``merge_contextvars``).
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import MutableMapping
from functools import partial
from typing import Any

import structlog

_FALLBACK_FORMAT = "%(asctime)s [%(name)s] %(levelname)s %(message)s"
_FALLBACK_DATEFMT = "%Y-%m-%d %H:%M:%S"

# Module-name segments that carry no information — fall back to the parent.
_DEFAULT_SKIP = ("__init__",)


def _short_module(name: str, skip_suffixes: tuple[str, ...]) -> str:
    parts = name.split(".")
    tag = parts[-1]
    if tag in skip_suffixes and len(parts) >= 2:
        tag = parts[-2]
    return tag


def _make_add_meta(
    service_name: str,
    own_prefixes: tuple[str, ...],
    skip_suffixes: tuple[str, ...],
) -> Any:
    """structlog processor: add ``service`` / ``mod`` / ``own`` from the logger name.

    Replaces the old _ModuleFormatter, without mutating the LogRecord.
    """

    def _add_meta(
        _: Any, __: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        event_dict.setdefault("service", service_name)
        logger_name = str(event_dict.get("logger") or "")
        event_dict["mod"] = _short_module(logger_name, skip_suffixes)
        event_dict["own"] = bool(own_prefixes) and logger_name.startswith(own_prefixes)
        return event_dict

    return _add_meta


def _drop_exc(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Strip traceback keys — the Discord webhook handler appends its own."""
    for key in ("exc_info", "exception", "stack"):
        event_dict.pop(key, None)
    return event_dict


def _shared_processors(
    service_name: str,
    own_prefixes: tuple[str, ...],
    skip_suffixes: tuple[str, ...],
) -> list[Any]:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.ExtraAdder(),
        _make_add_meta(service_name, own_prefixes, skip_suffixes),
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        structlog.processors.StackInfoRenderer(),
    ]


def _build_formatter(shared: list[Any], *, console: bool) -> structlog.stdlib.ProcessorFormatter:
    render_chain: list[Any]
    if console:
        render_chain = [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        render_chain = [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            # ensure_ascii=False: user_message and channel names are CJK.
            structlog.processors.JSONRenderer(
                serializer=partial(json.dumps, ensure_ascii=False, default=str)
            ),
        ]
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=render_chain,
    )


def setup_logging(
    log_level: str = "INFO",
    webhook_url: str = "",
    service_name: str = "niibot",
    suppress_loggers: dict[str, int] | None = None,
    own_prefixes: tuple[str, ...] = (),
    skip_suffixes: tuple[str, ...] = _DEFAULT_SKIP,
    console: bool = False,
) -> None:
    """Configure application logging.

    Args:
        log_level: Log level string (e.g. ``"INFO"``, ``"DEBUG"``).
        webhook_url: Discord webhook URL for ERROR+ alerts. Empty = disabled.
        service_name: ``"api"`` / ``"discord"`` / ``"twitch"``. Emitted as the
            ``service`` field and used in webhook payloads.
        suppress_loggers: Mapping of logger name → level for noise reduction.
        own_prefixes: Logger-name prefixes treated as first-party (``own=true``).
        skip_suffixes: Module-name segments to skip when building ``mod``.
        console: Human-readable coloured output (local dev). Otherwise JSON.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    shared = _shared_processors(service_name, own_prefixes, tuple(skip_suffixes))

    # Make native structlog.get_logger() calls (rare) share the same pipeline.
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    try:
        if sys.platform == "win32":
            import codecs

            if hasattr(sys.stdout, "buffer"):
                sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer)
            if hasattr(sys.stderr, "buffer"):
                sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer)

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_build_formatter(shared, console=console))
        logging.basicConfig(level=level, handlers=[handler], force=True)
    except Exception as e:  # pragma: no cover - defensive
        logging.basicConfig(
            level=level,
            format=_FALLBACK_FORMAT,
            datefmt=_FALLBACK_DATEFMT,
            force=True,
        )
        logging.getLogger(__name__).warning("structlog setup failed: %s, using standard logging", e)

    # Discord webhook handler for ERROR+ alerts — its own formatter so the
    # embed shows the rendered event + bound context, not a dict repr.
    if webhook_url:
        from shared.discord_webhook_handler import DiscordWebhookHandler

        webhook_handler = DiscordWebhookHandler(webhook_url, service_name=service_name)
        webhook_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                foreign_pre_chain=shared,
                processors=[
                    _drop_exc,
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.dev.ConsoleRenderer(colors=False),
                ],
            )
        )
        logging.getLogger().addHandler(webhook_handler)

    if suppress_loggers:
        for name, lvl in suppress_loggers.items():
            logging.getLogger(name).setLevel(lvl)
