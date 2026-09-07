"""Unit tests for the chat `!vq <url>` add handler.

Covers `VideoQueueComponent._handle_add_inner`
(backend/twitch/components/video_queue.py) — specifically the submission gates
that need fetched metadata (min view count, global length cap) and their
best-effort handling, which must match the redemption and dashboard paths
(see test_channel_points_video_queue.py and test_video_queue_router.py).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from twitch.components.video_queue import VideoQueueComponent

from shared.models.video_queue import VideoQueueEntry, VideoQueueSettings
from shared.video_sources import ResolvedVideo, VideoMetadata

CHANNEL_ID = "channel-1"


def _bot() -> MagicMock:
    bot = MagicMock()
    bot.token_database = MagicMock()
    return bot


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.channel.id = CHANNEL_ID
    ctx.chatter.moderator = True
    ctx.chatter.broadcaster = False
    ctx.chatter.display_name = "Mod"
    ctx.chatter.name = "mod"
    ctx.chatter.id = "mod-1"
    return ctx


def _settings(**kw) -> VideoQueueSettings:
    return VideoQueueSettings(
        channel_id=CHANNEL_ID,
        enabled=kw.get("enabled", True),
        min_view_count=kw.get("min_view_count", 0),
        max_duration_seconds=kw.get("max_duration_seconds", 0),
        max_queue_size=kw.get("max_queue_size", 20),
        max_per_user=kw.get("max_per_user", 0),
        user_cooldown_seconds=kw.get("user_cooldown_seconds", 0),
        replay_cooldown_hours=kw.get("replay_cooldown_hours", 0),
    )


def _entry() -> VideoQueueEntry:
    return VideoQueueEntry(
        id=1,
        channel_id=CHANNEL_ID,
        video_id="vid123",
        requested_by="Mod",
        source="chat",
        status="queued",
        video_type="bilibili",
        title="T",
        duration_seconds=None,
        created_at=datetime.now(UTC),
    )


def _component(*, settings: VideoQueueSettings | None = None) -> VideoQueueComponent:
    component = VideoQueueComponent(_bot())
    component.vq_settings_repo.get_or_create = AsyncMock(return_value=settings or _settings())
    component.vq_repo.video_is_active = AsyncMock(return_value=False)
    component.vq_repo.get_queue_size = AsyncMock(return_value=1)
    component.vq_repo.count_active_by_user = AsyncMock(return_value=0)
    component.vq_repo.find_last_entry_by_user = AsyncMock(return_value=None)
    component.vq_repo.played_within = AsyncMock(return_value=False)
    component.vq_repo.add_if_within_limits = AsyncMock(return_value=_entry())
    component.vq_blocklist_repo.check = AsyncMock(return_value=None)
    component._ctx_reply = AsyncMock()  # type: ignore[method-assign]
    return component


def _patches(component: VideoQueueComponent, resolved: ResolvedVideo, metadata: VideoMetadata):
    return (
        patch("twitch.components.video_queue.resolve_video_url", AsyncMock(return_value=resolved)),
        patch(
            "twitch.components.video_queue.fetch_video_metadata",
            AsyncMock(return_value=metadata),
        ),
    )


@pytest.mark.asyncio
class TestChatAddMetadataGates:
    async def test_missing_view_count_rejected_for_authoritative_source(self):
        component = _component(settings=_settings(min_view_count=1000))
        p1, p2 = _patches(
            component,
            ResolvedVideo("youtube", "vid123", False),
            VideoMetadata("YT", 90, None, False),
        )
        with p1, p2:
            await component._handle_add_inner(_ctx(), "https://youtube.com/watch?v=vid123")
        component.vq_repo.add_if_within_limits.assert_not_awaited()
        assert component._ctx_reply.await_args.args[1] == "無法驗證影片資訊，請稍後再試"

    async def test_missing_view_count_allowed_for_best_effort_platform(self):
        component = _component(settings=_settings(min_view_count=1000))
        p1, p2 = _patches(
            component,
            ResolvedVideo("bilibili", "BV1x", False),
            VideoMetadata("BV", None, None, False, metadata_best_effort=True),
        )
        with p1, p2:
            await component._handle_add_inner(_ctx(), "https://bilibili.com/video/BV1x")
        component.vq_repo.add_if_within_limits.assert_awaited_once()

    async def test_missing_duration_rejected_for_authoritative_source(self):
        component = _component(settings=_settings(max_duration_seconds=600))
        p1, p2 = _patches(
            component,
            ResolvedVideo("youtube", "vid123", False),
            VideoMetadata("YT", None, 5000, False),
        )
        with p1, p2:
            await component._handle_add_inner(_ctx(), "https://youtube.com/watch?v=vid123")
        component.vq_repo.add_if_within_limits.assert_not_awaited()

    async def test_missing_duration_allowed_for_best_effort_platform(self):
        component = _component(settings=_settings(max_duration_seconds=600))
        p1, p2 = _patches(
            component,
            ResolvedVideo("bilibili", "BV1FjxHzGEkQ", False),
            VideoMetadata("BV", None, None, False, metadata_best_effort=True),
        )
        with p1, p2:
            await component._handle_add_inner(_ctx(), "https://bilibili.com/video/BV1FjxHzGEkQ")
        component.vq_repo.add_if_within_limits.assert_awaited_once()

    async def test_known_duration_still_capped_for_best_effort_platform(self):
        component = _component(settings=_settings(max_duration_seconds=600))
        p1, p2 = _patches(
            component,
            ResolvedVideo("bilibili", "BV1x", False),
            VideoMetadata("BV", 9999, 5000, False, metadata_best_effort=True),
        )
        with p1, p2:
            await component._handle_add_inner(_ctx(), "https://bilibili.com/video/BV1x")
        component.vq_repo.add_if_within_limits.assert_not_awaited()
