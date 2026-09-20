"""API cache invalidation for versioned assistant scope notifications."""

from __future__ import annotations

from unittest.mock import MagicMock

import services.assistant_scope_notifications as notification_handler
from shared.assistant import AssistantMode, AssistantScopeChange


async def test_scope_change_invalidates_only_the_named_ai_settings_cache(monkeypatch) -> None:
    invalidate = MagicMock()
    monkeypatch.setattr(notification_handler, "invalidate_ai_settings_cache", invalidate)
    payload = AssistantScopeChange(
        channel_id="channel-a",
        assistant_mode=AssistantMode.ROLEPLAY,
        active_roleplay_revision_id=41,
    ).to_payload()

    await notification_handler.handle_assistant_scope_changed_notify(None, 1, "scope", payload)

    invalidate.assert_called_once_with("channel-a")


async def test_malformed_scope_change_is_ignored_without_broad_cache_clear(monkeypatch) -> None:
    invalidate = MagicMock()
    monkeypatch.setattr(notification_handler, "invalidate_ai_settings_cache", invalidate)

    await notification_handler.handle_assistant_scope_changed_notify(
        None, 1, "scope", '{"token":"x"}'
    )

    invalidate.assert_not_called()
