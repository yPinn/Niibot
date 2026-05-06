"""Reauth notification utility for scope-missing Helix errors.

Usage in a component:
    from utils.reauth import is_scope_error, reauth_notifier

    response = await self.bot._http.post_chat_shoutout(...)
    if is_scope_error(response):
        await reauth_notifier.notify(
            broadcaster_login=broadcaster_name,
            channel_id=channel_id,
            send_fn=lambda msg: channel.send_message(
                message=msg,
                sender=self.bot.bot_id,
            ),
        )
        return
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from core.config import get_settings
from shared.twitch_scopes import BROADCASTER_SCOPES

LOGGER: logging.Logger = logging.getLogger(__name__)

_COOLDOWN = timedelta(hours=1)


def is_scope_error(obj: object) -> bool:
    """Return True if a response or exception indicates a missing OAuth scope.

    Handles both httpx.Response objects and TwitchIO HTTPException exceptions,
    which carry .status (int) and .message (str) rather than .status_code.
    """
    if obj is None:
        return False
    status = getattr(obj, "status_code", None) or getattr(obj, "status", None)
    if status != 401:
        return False
    # Named attributes first (fastest, covers TwitchIO HTTPException)
    for attr in ("message", "reason"):
        val = getattr(obj, attr, None)
        if isinstance(val, str) and "Missing scope" in val:
            return True
    # httpx.Response: parse JSON body
    try:
        body = obj.json() if callable(getattr(obj, "json", None)) else {}  # type: ignore[attr-defined]
        if "Missing scope" in body.get("message", ""):
            return True
    except Exception:
        pass
    # Last resort: stringify
    return "Missing scope" in str(obj)


class ReauthNotifier:
    """Rate-limits reauth chat notifications to once per channel per hour."""

    def __init__(self) -> None:
        self._last_notified: dict[str, datetime] = {}

    def _can_notify(self, channel_id: str) -> bool:
        last = self._last_notified.get(channel_id)
        return last is None or datetime.now(UTC) - last >= _COOLDOWN

    def _build_message(self, broadcaster_login: str) -> str:
        url = get_settings().frontend_url.rstrip("/")
        return f"@{broadcaster_login} 請重新登入以恢復功能：{url}"

    async def notify(
        self,
        broadcaster_login: str,
        channel_id: str,
        send_fn: Callable[[str], Awaitable[object]],
    ) -> bool:
        """Send a reauth notification if cooldown permits. Returns True if sent."""
        if not self._can_notify(channel_id):
            return False
        self._last_notified[channel_id] = datetime.now(UTC)
        try:
            await send_fn(self._build_message(broadcaster_login))
            LOGGER.info(f"[{broadcaster_login}] Reauth notification sent")
        except Exception:
            LOGGER.exception(f"[{broadcaster_login}] Failed to send reauth notification")
        return True


reauth_notifier = ReauthNotifier()


def missing_broadcaster_scopes(scopes: list[str] | set[str]) -> list[str]:
    """Return BROADCASTER_SCOPES entries absent from *scopes*."""
    return [s for s in BROADCASTER_SCOPES if s not in scopes]
