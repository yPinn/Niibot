"""Unit tests for ChannelPointsComponent's video queue redemption handler.

Covers the three-platform happy path through `_handle_video_queue_redemption`
(backend/twitch/components/channel_points.py) — previously untested despite
sharing the same resolve/fetch registry as the chat `!vq` command and the
dashboard "add video" endpoint (see test_video_sources_registry.py and
test_video_queue_router.py::TestAddVideoEntry for those).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from twitch.components.channel_points import ChannelPointsComponent

from shared.models.video_queue import VideoQueueEntry, VideoQueueSettings
from shared.video_sources import ResolvedVideo, VideoMetadata

CHANNEL_ID = "channel-1"


def _bot() -> MagicMock:
    bot = MagicMock()
    bot.token_database = MagicMock()
    return bot


def _payload(*, user_input: str) -> MagicMock:
    payload = MagicMock()
    payload.id = "redemption-vq-1"
    payload.broadcaster.id = CHANNEL_ID
    payload.broadcaster.name = "streamer"
    payload.user.id = "viewer-1"
    payload.user.name = "viewer"
    payload.user.display_name = "Viewer"
    payload.reward.title = "點歌"
    payload.reward.cost = 100
    payload.user_input = user_input
    return payload


def _settings(**kw) -> VideoQueueSettings:
    return VideoQueueSettings(
        channel_id=CHANNEL_ID,
        enabled=kw.get("enabled", True),
        redemption_enabled=kw.get("redemption_enabled", True),
        max_duration_redemption=kw.get("max_duration_redemption", 0),
        max_queue_size=kw.get("max_queue_size", 20),
        min_view_count=kw.get("min_view_count", 0),
        user_cooldown_seconds=kw.get("user_cooldown_seconds", 0),
        max_per_user=kw.get("max_per_user", 0),
        max_duration_seconds=kw.get("max_duration_seconds", 0),
    )


def _entry(**kw) -> VideoQueueEntry:
    return VideoQueueEntry(
        id=1,
        channel_id=CHANNEL_ID,
        video_id=kw.get("video_id", "vid123"),
        requested_by="Viewer",
        source="redemption",
        status="queued",
        video_type=kw.get("video_type", "youtube"),
        title=kw.get("title"),
        duration_seconds=kw.get("duration_seconds"),
    )


def _component(*, settings: VideoQueueSettings | None = None) -> ChannelPointsComponent:
    component = ChannelPointsComponent(_bot())
    component.vq_settings_repo.get_or_create = AsyncMock(return_value=settings or _settings())
    component.vq_repo.video_is_active = AsyncMock(return_value=False)
    component.vq_repo.get_queue_size = AsyncMock(return_value=1)
    component.vq_repo.count_active_by_user = AsyncMock(return_value=0)
    component.vq_repo.find_last_entry_by_user = AsyncMock(return_value=None)
    component.vq_repo.add_if_within_limits = AsyncMock(return_value=_entry())
    component.vq_blocklist_repo.check = AsyncMock(return_value=None)
    component._reply = AsyncMock()  # type: ignore[method-assign]
    return component


@pytest.mark.asyncio
class TestVideoQueueRedemptionPlatforms:
    async def test_youtube_happy_path(self):
        component = _component()
        resolved = ResolvedVideo("youtube", "vid123", False)
        metadata = VideoMetadata("YT Title", 120, 5000, False)
        with (
            patch(
                "twitch.components.channel_points.resolve_video_url",
                AsyncMock(return_value=resolved),
            ),
            patch(
                "twitch.components.channel_points.fetch_video_metadata",
                AsyncMock(return_value=metadata),
            ),
        ):
            await component._handle_video_queue_redemption(
                _payload(user_input="https://youtube.com/watch?v=vid123"), "Viewer"
            )
        component.vq_repo.add_if_within_limits.assert_awaited_once()
        kwargs = component.vq_repo.add_if_within_limits.await_args.kwargs
        assert kwargs["video_id"] == "vid123"
        assert kwargs["video_type"] == "youtube"
        assert kwargs["title"] == "YT Title"
        assert kwargs["duration_seconds"] == 120

    async def test_twitch_clip_happy_path(self):
        component = _component()
        resolved = ResolvedVideo("twitch_clip", "AwesomeClip", False)
        metadata = VideoMetadata("Clip Title", 30, 200, False)
        with (
            patch(
                "twitch.components.channel_points.resolve_video_url",
                AsyncMock(return_value=resolved),
            ),
            patch(
                "twitch.components.channel_points.fetch_video_metadata",
                AsyncMock(return_value=metadata),
            ),
        ):
            await component._handle_video_queue_redemption(
                _payload(user_input="https://clips.twitch.tv/AwesomeClip"), "Viewer"
            )
        kwargs = component.vq_repo.add_if_within_limits.await_args.kwargs
        assert kwargs["video_id"] == "AwesomeClip"
        assert kwargs["video_type"] == "twitch_clip"
        assert kwargs["is_vertical"] is False

    async def test_bilibili_happy_path(self):
        component = _component()
        resolved = ResolvedVideo("bilibili", "BV1xx411c7mD", False)
        metadata = VideoMetadata("BV Title", 90, 10000, True)
        with (
            patch(
                "twitch.components.channel_points.resolve_video_url",
                AsyncMock(return_value=resolved),
            ),
            patch(
                "twitch.components.channel_points.fetch_video_metadata",
                AsyncMock(return_value=metadata),
            ),
        ):
            await component._handle_video_queue_redemption(
                _payload(user_input="https://www.bilibili.com/video/BV1xx411c7mD"), "Viewer"
            )
        kwargs = component.vq_repo.add_if_within_limits.await_args.kwargs
        assert kwargs["video_id"] == "BV1xx411c7mD"
        assert kwargs["video_type"] == "bilibili"
        assert kwargs["is_vertical"] is True

    async def test_unresolvable_url_replies_and_does_not_queue(self):
        component = _component()
        with patch(
            "twitch.components.channel_points.resolve_video_url",
            AsyncMock(return_value=None),
        ):
            await component._handle_video_queue_redemption(
                _payload(user_input="not a url"), "Viewer"
            )
        component.vq_repo.add_if_within_limits.assert_not_awaited()
        component._reply.assert_awaited_once()

    async def test_surrounding_whitespace_is_trimmed_before_resolving(self):
        # Twitch's redemption text box returns the raw typed text — a stray
        # leading/trailing space must not be forwarded as part of the URL
        # (resolve_video_url itself also tolerates it, but the chat !vq path
        # trims too, and the two should behave identically).
        component = _component()
        resolved = ResolvedVideo("youtube", "vid123", False)
        metadata = VideoMetadata("YT Title", 120, 5000, False)
        resolve_mock = AsyncMock(return_value=resolved)
        with (
            patch("twitch.components.channel_points.resolve_video_url", resolve_mock),
            patch(
                "twitch.components.channel_points.fetch_video_metadata",
                AsyncMock(return_value=metadata),
            ),
        ):
            await component._handle_video_queue_redemption(
                _payload(user_input="  https://youtube.com/watch?v=vid123  "), "Viewer"
            )
        resolve_mock.assert_awaited_once_with(
            "https://youtube.com/watch?v=vid123", session=component._session
        )
        component.vq_repo.add_if_within_limits.assert_awaited_once()

    async def test_unplayable_video_replies_and_does_not_queue(self):
        component = _component()
        resolved = ResolvedVideo("youtube", "vid123", False)
        metadata = VideoMetadata(
            "Restricted",
            120,
            5000,
            False,
            playable=False,
            unplayable_reason="not_embeddable",
        )
        with (
            patch(
                "twitch.components.channel_points.resolve_video_url",
                AsyncMock(return_value=resolved),
            ),
            patch(
                "twitch.components.channel_points.fetch_video_metadata",
                AsyncMock(return_value=metadata),
            ),
        ):
            await component._handle_video_queue_redemption(
                _payload(user_input="https://youtube.com/watch?v=vid123"), "Viewer"
            )
        component.vq_repo.add_if_within_limits.assert_not_awaited()
        component._reply.assert_awaited_once()

    async def test_blocked_video_replies_and_does_not_queue(self):
        component = _component()
        component.vq_blocklist_repo.check = AsyncMock(
            return_value=MagicMock(kind="keyword", value="lofi")
        )
        with (
            patch(
                "twitch.components.channel_points.resolve_video_url",
                AsyncMock(return_value=ResolvedVideo("youtube", "vid123", False)),
            ),
            patch(
                "twitch.components.channel_points.fetch_video_metadata",
                AsyncMock(return_value=VideoMetadata("chill lofi", 120, 5000, False)),
            ),
        ):
            await component._handle_video_queue_redemption(
                _payload(user_input="https://youtube.com/watch?v=vid123"), "Viewer"
            )
        component.vq_repo.add_if_within_limits.assert_not_awaited()
        component._reply.assert_awaited_once()

    async def test_redemption_disabled_does_not_resolve_url(self):
        component = _component(settings=_settings(redemption_enabled=False))
        with patch(
            "twitch.components.channel_points.resolve_video_url",
            AsyncMock(return_value=None),
        ) as mock_resolve:
            await component._handle_video_queue_redemption(
                _payload(user_input="https://youtube.com/watch?v=vid123"), "Viewer"
            )
        mock_resolve.assert_not_awaited()
        component.vq_repo.add_if_within_limits.assert_not_awaited()

    async def test_missing_view_count_rejected_for_authoritative_source(self):
        # min_view_count>0 with an unknown view_count from an official API is a
        # transient failure — reject rather than silently bypass the filter.
        component = _component(settings=_settings(min_view_count=1000))
        resolved = ResolvedVideo("youtube", "vid123", False)
        metadata = VideoMetadata("YT Title", 90, None, False)  # not best-effort
        with (
            patch(
                "twitch.components.channel_points.resolve_video_url",
                AsyncMock(return_value=resolved),
            ),
            patch(
                "twitch.components.channel_points.fetch_video_metadata",
                AsyncMock(return_value=metadata),
            ),
        ):
            await component._handle_video_queue_redemption(
                _payload(user_input="https://youtube.com/watch?v=vid123"), "Viewer"
            )
        component.vq_repo.add_if_within_limits.assert_not_awaited()
        component._reply.assert_awaited_once()

    async def test_missing_view_count_allowed_for_best_effort_platform(self):
        # Bilibili's unofficial endpoint (412) can never supply a view_count, so
        # min_view_count must skip rather than reject every Bilibili redemption.
        component = _component(settings=_settings(min_view_count=1000))
        resolved = ResolvedVideo("bilibili", "BV1xx411c7mD", False)
        metadata = VideoMetadata("BV Title", None, None, False, metadata_best_effort=True)
        with (
            patch(
                "twitch.components.channel_points.resolve_video_url",
                AsyncMock(return_value=resolved),
            ),
            patch(
                "twitch.components.channel_points.fetch_video_metadata",
                AsyncMock(return_value=metadata),
            ),
        ):
            await component._handle_video_queue_redemption(
                _payload(user_input="https://www.bilibili.com/video/BV1xx411c7mD"), "Viewer"
            )
        component.vq_repo.add_if_within_limits.assert_awaited_once()

    async def test_missing_duration_rejected_for_authoritative_source(self):
        component = _component(settings=_settings(max_duration_redemption=600))
        resolved = ResolvedVideo("youtube", "vid123", False)
        metadata = VideoMetadata("YT Title", None, 5000, False)  # not best-effort
        with (
            patch(
                "twitch.components.channel_points.resolve_video_url",
                AsyncMock(return_value=resolved),
            ),
            patch(
                "twitch.components.channel_points.fetch_video_metadata",
                AsyncMock(return_value=metadata),
            ),
        ):
            await component._handle_video_queue_redemption(
                _payload(user_input="https://youtube.com/watch?v=vid123"), "Viewer"
            )
        component.vq_repo.add_if_within_limits.assert_not_awaited()
        component._reply.assert_awaited_once()

    async def test_missing_duration_allowed_for_best_effort_platform(self):
        # The reported bug: every Bilibili redemption rejected once a cap is set.
        component = _component(
            settings=_settings(max_duration_redemption=600, max_duration_seconds=1200)
        )
        resolved = ResolvedVideo("bilibili", "BV1FjxHzGEkQ", False)
        metadata = VideoMetadata("BV Title", None, None, False, metadata_best_effort=True)
        with (
            patch(
                "twitch.components.channel_points.resolve_video_url",
                AsyncMock(return_value=resolved),
            ),
            patch(
                "twitch.components.channel_points.fetch_video_metadata",
                AsyncMock(return_value=metadata),
            ),
        ):
            await component._handle_video_queue_redemption(
                _payload(user_input="https://www.bilibili.com/video/BV1FjxHzGEkQ"), "Viewer"
            )
        component.vq_repo.add_if_within_limits.assert_awaited_once()

    async def test_known_duration_still_capped_for_best_effort_platform(self):
        # When Bilibili *does* return a duration, the cap still applies.
        component = _component(settings=_settings(max_duration_redemption=600))
        resolved = ResolvedVideo("bilibili", "BV1xx411c7mD", False)
        metadata = VideoMetadata("BV Title", 9999, 5000, False, metadata_best_effort=True)
        with (
            patch(
                "twitch.components.channel_points.resolve_video_url",
                AsyncMock(return_value=resolved),
            ),
            patch(
                "twitch.components.channel_points.fetch_video_metadata",
                AsyncMock(return_value=metadata),
            ),
        ):
            await component._handle_video_queue_redemption(
                _payload(user_input="https://www.bilibili.com/video/BV1xx411c7mD"), "Viewer"
            )
        component.vq_repo.add_if_within_limits.assert_not_awaited()
        component._reply.assert_awaited_once()

    async def test_title_falls_back_to_video_id_when_metadata_has_no_title(self):
        # Regression guard for the `title or resolved.video_id` log line —
        # must not reference a stale `video_id` local (previously removed
        # when the platform cascade was collapsed into resolve_video_url()).
        component = _component()
        resolved = ResolvedVideo("bilibili", "BV1xx411c7mD", False)
        metadata = VideoMetadata(None, 90, 10000, False)
        with (
            patch(
                "twitch.components.channel_points.resolve_video_url",
                AsyncMock(return_value=resolved),
            ),
            patch(
                "twitch.components.channel_points.fetch_video_metadata",
                AsyncMock(return_value=metadata),
            ),
        ):
            await component._handle_video_queue_redemption(
                _payload(user_input="https://www.bilibili.com/video/BV1xx411c7mD"), "Viewer"
            )
        component.vq_repo.add_if_within_limits.assert_awaited_once()
        component._reply.assert_awaited()
