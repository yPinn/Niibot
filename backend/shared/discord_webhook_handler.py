"""Discord webhook logging handler.

Sends ERROR and CRITICAL log records to a Discord webhook channel.
Uses a daemon thread + urllib so it never blocks the event loop.
"""

from __future__ import annotations

import json
import logging
import threading
import traceback
import urllib.request
from datetime import UTC, datetime

_LEVEL_COLORS = {
    logging.WARNING: 0xFFAA00,
    logging.ERROR: 0xFF4444,
    logging.CRITICAL: 0xFF0000,
}

_LEVEL_EMOJI = {
    logging.WARNING: "⚠️",
    logging.ERROR: "🔴",
    logging.CRITICAL: "💀",
}


class DiscordWebhookHandler(logging.Handler):
    """Logging handler that POSTs ERROR/CRITICAL records to a Discord webhook.

    Thread-safe: each emit spawns a daemon thread so the caller is never blocked.
    Send failures are silently swallowed to avoid log→error→log recursion.

    Usage::

        handler = DiscordWebhookHandler(webhook_url, service_name="api")
        logging.getLogger().addHandler(handler)
    """

    def __init__(self, webhook_url: str, service_name: str = "niibot") -> None:
        super().__init__(level=logging.ERROR)
        self._url = webhook_url
        self._service = service_name
        # Plain formatter — Rich markup is stripped, Discord gets clean text
        self.setFormatter(logging.Formatter("%(message)s"))

    # ------------------------------------------------------------------
    # logging.Handler interface
    # ------------------------------------------------------------------

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = self._build_payload(record)
        except Exception:
            self.handleError(record)
            return

        threading.Thread(target=self._post, args=(payload,), daemon=True).start()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_payload(self, record: logging.LogRecord) -> bytes:
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()

        description = message[:1800]  # leave room for traceback block

        if record.exc_info:
            tb_lines = traceback.format_exception(*record.exc_info)
            tb_text = "".join(tb_lines)
            # Discord embed description cap: 4096 chars
            max_tb = 4096 - len(description) - 10
            if max_tb > 50:
                description += f"\n```\n{tb_text[:max_tb]}\n```"

        color = _LEVEL_COLORS.get(record.levelno, 0xFF4444)
        emoji = _LEVEL_EMOJI.get(record.levelno, "🔴")

        payload = {
            "embeds": [
                {
                    "title": f"{emoji} [{self._service.upper()}] {record.levelname}",
                    "description": description[:4096],
                    "color": color,
                    "fields": [
                        {"name": "Logger", "value": record.name, "inline": True},
                        {"name": "Service", "value": self._service, "inline": True},
                    ],
                    "timestamp": datetime.now(UTC).isoformat(),
                    "footer": {"text": f"{self._service} • error-webhook"},
                }
            ]
        }

        return json.dumps(payload).encode()

    def _post(self, payload: bytes) -> None:
        try:
            req = urllib.request.Request(
                self._url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception:
            pass  # never propagate — would cause log→error→log loop
