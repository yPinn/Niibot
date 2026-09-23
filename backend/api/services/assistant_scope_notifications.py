"""API-side cache reaction to versioned assistant scope notifications."""

from __future__ import annotations

import logging

from shared.assistant import AssistantScopeChange
from shared.cache_invalidation import invalidate_ai_settings_cache

LOGGER: logging.Logger = logging.getLogger(__name__)


async def handle_assistant_scope_changed_notify(connection, pid, channel, payload) -> None:
    """Invalidate only the assistant settings cache for a valid scope change."""
    try:
        change = AssistantScopeChange.from_payload(payload)
        invalidate_ai_settings_cache(change.channel_id)
        LOGGER.info(
            "assistant_scope_change_invalidated",
            extra={
                "channel_id": change.channel_id,
                "assistant_mode": change.assistant_mode.value,
                "active_roleplay_revision_id": change.active_roleplay_revision_id,
            },
        )
    except ValueError:
        LOGGER.warning("assistant_scope_change_invalid_payload")
