"""Mod-status guard — blocks bot features until channel grants mod, with rate-limited prompt."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from core.config import get_settings

LOGGER: logging.Logger = logging.getLogger(__name__)

_COOLDOWN = timedelta(hours=1)


class ModGuardNotifier:
    """Rate-limits 'bot needs mod' notifications to once per hour per channel."""

    def __init__(self) -> None:
        self._last_notified: dict[str, datetime] = {}

    def _can_notify(self, channel_id: str) -> bool:
        last = self._last_notified.get(channel_id)
        return last is None or datetime.now(UTC) - last >= _COOLDOWN

    async def notify(
        self,
        broadcaster_login: str,
        channel_id: str,
        bot_login: str,
        send_fn: Callable[[str], Awaitable[object]],
    ) -> bool:
        """Send a /mod prompt if cooldown permits. Returns True if sent."""
        if get_settings().is_development:
            LOGGER.debug(f"[{broadcaster_login}] Mod guard notification skipped (dev)")
            return False
        if not self._can_notify(channel_id):
            return False
        self._last_notified[channel_id] = datetime.now(UTC)
        msg = (
            f"@{broadcaster_login} 請在聊天室輸入 /mod {bot_login} 授予管理員身分，"
            "以啟用機器人所有功能！"
        )
        try:
            await send_fn(msg)
            LOGGER.info(f"[{broadcaster_login}] Mod guard notification sent")
        except Exception:
            LOGGER.exception(f"[{broadcaster_login}] Failed to send mod guard notification")
        return True


mod_guard_notifier = ModGuardNotifier()
