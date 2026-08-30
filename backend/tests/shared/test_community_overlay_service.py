"""Tests for community overlay publishing orchestration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from shared.community_overlay_themes import DEFAULT_OVERLAY_THEME
from shared.services.community_overlay import CommunityOverlayService

_NOW = datetime(2026, 8, 31, 10, 0, tzinfo=UTC)


@pytest.mark.asyncio
class TestPublishCheckinPreview:
    async def test_publishes_short_lived_event_without_checkin_ledger(self) -> None:
        repo = MagicMock()
        repo.get_or_create_channel = AsyncMock()
        repo.publish_event = AsyncMock(return_value=91)
        service = CommunityOverlayService(repo)

        event_id = await service.publish_checkin_preview(
            channel_id="ch1",
            actor_user_id="owner1",
            actor_display_name="Streamer",
            total_days=8,
            occurred_at=_NOW,
        )

        assert event_id == 91
        repo.get_or_create_channel.assert_awaited_once_with("ch1")
        kwargs = repo.publish_event.await_args.kwargs
        assert kwargs["channel_id"] == "ch1"
        assert kwargs["event_type"] == "checkin.recorded"
        assert kwargs["schema_version"] == 1
        assert kwargs["source"] == "system"
        assert kwargs["payload"] == {
            "total_days": 8,
            "checkin_date": "2026-08-31",
            "preview": True,
        }
        assert kwargs["expires_at"] == _NOW + timedelta(minutes=10)
        assert kwargs["idempotency_key"].startswith("dev-checkin:")

    @pytest.mark.parametrize("count", [0, 10_000])
    async def test_rejects_unreasonable_preview_count(self, count: int) -> None:
        repo = MagicMock()
        repo.get_or_create_channel = AsyncMock()
        repo.publish_event = AsyncMock()
        service = CommunityOverlayService(repo)

        with pytest.raises(ValueError, match="between 1 and 9999"):
            await service.publish_checkin_preview(
                channel_id="ch1",
                actor_user_id="owner1",
                actor_display_name="Streamer",
                total_days=count,
                occurred_at=_NOW,
            )

        repo.publish_event.assert_not_awaited()

    async def test_rejects_naive_preview_timestamp(self) -> None:
        repo = MagicMock()
        repo.get_or_create_channel = AsyncMock()
        repo.publish_event = AsyncMock()
        service = CommunityOverlayService(repo)

        with pytest.raises(ValueError, match="timezone-aware"):
            await service.publish_checkin_preview(
                channel_id="ch1",
                actor_user_id="owner1",
                actor_display_name="Streamer",
                total_days=1,
                occurred_at=datetime(2026, 8, 31, 10, 0),
            )


@pytest.mark.asyncio
async def test_access_and_feed_methods_delegate_to_repository() -> None:
    repo = MagicMock()
    repo.get_or_create_channel = AsyncMock(return_value="access")
    repo.rotate_public_key = AsyncMock(return_value="rotated")
    repo.set_enabled = AsyncMock(return_value="disabled")
    repo.get_feed = AsyncMock(return_value="feed")
    service = CommunityOverlayService(repo)

    assert await service.get_or_create_channel("ch1") == "access"
    assert await service.rotate_public_key("ch1") == "rotated"
    assert await service.set_enabled("ch1", False) == "disabled"
    assert (
        await service.get_feed(UUID("11111111-1111-4111-8111-111111111111"), after_id=7, limit=25)
        == "feed"
    )
    repo.set_enabled.assert_awaited_once_with("ch1", False)
    assert repo.get_feed.await_args.kwargs["after_id"] == 7
    assert repo.get_feed.await_args.kwargs["limit"] == 25


@pytest.mark.asyncio
class TestCommunityOverlayThemes:
    async def test_theme_methods_are_channel_scoped_and_public_lookup_uses_key(self) -> None:
        repo = MagicMock()
        repo.get_theme_state = AsyncMock(return_value="state")
        repo.publish_theme = AsyncMock(return_value="published")
        repo.reset_theme_draft = AsyncMock(return_value="reset")
        repo.get_public_theme = AsyncMock(return_value="public")
        service = CommunityOverlayService(repo)

        assert await service.get_theme_state("ch1") == "state"
        assert await service.publish_theme("ch1", 7) == "published"
        assert await service.reset_theme_draft("ch1", 7) == "reset"
        assert (
            await service.get_public_theme(UUID("11111111-1111-4111-8111-111111111111")) == "public"
        )

        repo.get_theme_state.assert_awaited_once_with("ch1")
        repo.publish_theme.assert_awaited_once_with("ch1", 7)
        repo.reset_theme_draft.assert_awaited_once_with("ch1", 7)

    async def test_update_draft_validates_and_normalizes_before_persistence(self) -> None:
        repo = MagicMock()
        repo.update_theme_draft = AsyncMock(return_value="updated")
        service = CommunityOverlayService(repo)

        result = await service.update_theme_draft(
            "ch1", {**DEFAULT_OVERLAY_THEME, "accent_color": "#ef4d88"}, 5
        )

        assert result == "updated"
        repo.update_theme_draft.assert_awaited_once_with(
            "ch1", {**DEFAULT_OVERLAY_THEME, "accent_color": "#EF4D88"}, 5
        )

    async def test_update_draft_rejects_unknown_fields_before_repository_call(self) -> None:
        repo = MagicMock()
        repo.update_theme_draft = AsyncMock()
        service = CommunityOverlayService(repo)

        with pytest.raises(ValueError, match="Unsupported theme fields"):
            await service.update_theme_draft(
                "ch1",
                {**DEFAULT_OVERLAY_THEME, "external_url": "https://example.com"},
                5,
            )

        repo.update_theme_draft.assert_not_awaited()
