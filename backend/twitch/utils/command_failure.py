"""Throttles repeated "this command failed" chat replies.

Unlike reauth (state-transition only, see utils/reauth.py), a command failure
has no persistent "broken" flag to key off — the same command can flip between
succeeding and failing per attempt. A short per-(channel, command) debounce
floor is the safety net here: it isn't trying to detect state transitions,
just to stop a sustained or flapping failure from re-announcing itself on
every single viewer attempt.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

LOGGER: logging.Logger = logging.getLogger(__name__)

_DEBOUNCE = timedelta(minutes=10)


class CommandFailureNotifier:
    """Rate-limits one command's failure reply per channel to once per debounce window."""

    def __init__(self) -> None:
        self._last_notified: dict[tuple[str, str], datetime] = {}

    def _can_notify(self, key: tuple[str, str]) -> bool:
        last = self._last_notified.get(key)
        return last is None or datetime.now(UTC) - last >= _DEBOUNCE

    async def notify(
        self,
        channel_id: str,
        command: str,
        message: str,
        send_fn: Callable[[str], Awaitable[object]],
    ) -> bool:
        """Send the failure reply if the debounce window permits. Returns True if sent."""
        key = (channel_id, command)
        if not self._can_notify(key):
            return False
        self._last_notified[key] = datetime.now(UTC)
        try:
            await send_fn(message)
        except Exception:
            LOGGER.exception(
                "Failed to send command-failure notification for %s/%s", channel_id, command
            )
        return True


command_failure_notifier = CommandFailureNotifier()
