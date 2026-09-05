"""Unit tests for the video_sources registry layer (resolve/fetch/build_watch_url).

These compose the already-tested platform-specific functions in video_sources.py
behind one shape — see TestFetchYtInfo etc. in test_video_queue_repo.py for
coverage of the underlying per-platform functions themselves.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from shared.video_sources import (
    ResolvedVideo,
    VideoMetadata,
    build_watch_url,
    fetch_video_metadata,
    resolve_video_url,
)

# ---------------------------------------------------------------------------
# resolve_video_url
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestResolveVideoUrl:
    async def test_youtube_url(self):
        resolved = await resolve_video_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert resolved == ResolvedVideo(
            video_type="youtube", video_id="dQw4w9WgXcQ", is_vertical=False
        )

    async def test_youtube_shorts_sets_is_vertical(self):
        resolved = await resolve_video_url("https://www.youtube.com/shorts/dQw4w9WgXcQ")
        assert resolved is not None
        assert resolved.video_type == "youtube"
        assert resolved.is_vertical is True

    async def test_twitch_clip_url(self):
        resolved = await resolve_video_url("https://clips.twitch.tv/SomeClipSlug")
        assert resolved == ResolvedVideo(
            video_type="twitch_clip", video_id="SomeClipSlug", is_vertical=False
        )

    async def test_bilibili_full_url(self):
        resolved = await resolve_video_url("https://www.bilibili.com/video/BV1xx411c7mD")
        assert resolved == ResolvedVideo(
            video_type="bilibili", video_id="BV1xx411c7mD", is_vertical=False
        )

    async def test_bilibili_short_url_resolves_via_redirect(self):
        with patch(
            "shared.video_sources.resolve_bilibili_url", new=AsyncMock(return_value="BV1xx411c7mD")
        ):
            resolved = await resolve_video_url("https://b23.tv/abc123")
        assert resolved == ResolvedVideo(
            video_type="bilibili", video_id="BV1xx411c7mD", is_vertical=False
        )

    async def test_unrecognized_url_returns_none(self):
        resolved = await resolve_video_url("https://example.com/not-a-video")
        assert resolved is None

    async def test_youtube_checked_before_twitch_and_bilibili(self):
        # A URL that could theoretically confuse ordering — YouTube regex must win
        # when a valid YouTube ID is present, matching the pre-existing cascade order.
        resolved = await resolve_video_url("https://youtu.be/dQw4w9WgXcQ some other text")
        assert resolved is not None
        assert resolved.video_type == "youtube"


# ---------------------------------------------------------------------------
# fetch_video_metadata — normalizes all three platforms to one 4-field shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFetchVideoMetadata:
    async def test_youtube_delegates_and_preserves_shape(self):
        resolved = ResolvedVideo(video_type="youtube", video_id="dQw4w9WgXcQ", is_vertical=False)
        with patch(
            "shared.video_sources.fetch_yt_info",
            new=AsyncMock(return_value=("Title", 120, 1000, False)),
        ) as mock_fetch:
            metadata = await fetch_video_metadata(resolved, youtube_api_key="key")
        mock_fetch.assert_awaited_once_with("dQw4w9WgXcQ", "key", None)
        assert metadata == VideoMetadata(
            title="Title", duration_seconds=120, view_count=1000, is_vertical=False
        )

    async def test_youtube_is_vertical_from_url_shape_or_api(self):
        # is_vertical is True if EITHER the URL shape (e.g. Shorts) OR the API says so.
        resolved = ResolvedVideo(video_type="youtube", video_id="dQw4w9WgXcQ", is_vertical=True)
        with patch(
            "shared.video_sources.fetch_yt_info",
            new=AsyncMock(return_value=("Title", 60, 500, False)),
        ):
            metadata = await fetch_video_metadata(resolved, youtube_api_key="key")
        assert metadata.is_vertical is True

    async def test_twitch_clip_normalizes_3tuple_to_4field_shape(self):
        resolved = ResolvedVideo(video_type="twitch_clip", video_id="SomeClipSlug")
        with patch(
            "shared.video_sources.fetch_twitch_clip_info",
            new=AsyncMock(return_value=("Clip Title", 30, 200)),
        ) as mock_fetch:
            metadata = await fetch_video_metadata(
                resolved, twitch_client_id="cid", twitch_client_secret="secret"
            )
        mock_fetch.assert_awaited_once_with("SomeClipSlug", "cid", "secret", None)
        assert metadata == VideoMetadata(
            title="Clip Title", duration_seconds=30, view_count=200, is_vertical=False
        )

    async def test_bilibili_delegates_and_preserves_shape(self):
        resolved = ResolvedVideo(video_type="bilibili", video_id="BV1xx411c7mD")
        with patch(
            "shared.video_sources.fetch_bilibili_info",
            new=AsyncMock(return_value=("BV Title", 90, 5000, True)),
        ) as mock_fetch:
            metadata = await fetch_video_metadata(resolved)
        mock_fetch.assert_awaited_once_with("BV1xx411c7mD", None)
        assert metadata == VideoMetadata(
            title="BV Title", duration_seconds=90, view_count=5000, is_vertical=True
        )

    async def test_fetch_failure_propagates_all_none(self):
        resolved = ResolvedVideo(video_type="youtube", video_id="dQw4w9WgXcQ")
        with patch(
            "shared.video_sources.fetch_yt_info",
            new=AsyncMock(return_value=(None, None, None, False)),
        ):
            metadata = await fetch_video_metadata(resolved, youtube_api_key="key")
        assert metadata == VideoMetadata(
            title=None, duration_seconds=None, view_count=None, is_vertical=False
        )


# ---------------------------------------------------------------------------
# build_watch_url
# ---------------------------------------------------------------------------


class TestBuildWatchUrl:
    def test_youtube(self):
        assert build_watch_url("youtube", "dQw4w9WgXcQ") == "https://youtu.be/dQw4w9WgXcQ"

    def test_twitch_clip(self):
        assert (
            build_watch_url("twitch_clip", "SomeClipSlug") == "https://clips.twitch.tv/SomeClipSlug"
        )

    def test_bilibili(self):
        # Regression test: !np previously fell through to the YouTube branch for
        # Bilibili entries, producing a broken https://youtu.be/BVxxxx link.
        assert (
            build_watch_url("bilibili", "BV1xx411c7mD")
            == "https://www.bilibili.com/video/BV1xx411c7mD"
        )

    def test_unknown_video_type_raises(self):
        with pytest.raises(ValueError, match="Unknown video_type"):
            build_watch_url("tiktok", "abc123")
