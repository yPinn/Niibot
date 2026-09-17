"""Unit tests for the video_sources registry layer (resolve/fetch/build_watch_url).

These compose the already-tested platform-specific functions in video_sources.py
behind one shape — see TestFetchYtInfo etc. in test_video_queue_repo.py for
coverage of the underlying per-platform functions themselves.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from shared.instafix_client import InstagramReelInfo
from shared.video_sources import (
    ResolvedVideo,
    VideoMetadata,
    YouTubeInfo,
    build_watch_url,
    fetch_video_metadata,
    metadata_gate_unverifiable,
    resolve_video_url,
)


class TestMetadataGateUnverifiable:
    def test_present_value_never_blocks(self):
        assert metadata_gate_unverifiable(0, best_effort=False) is False
        assert metadata_gate_unverifiable(100, best_effort=True) is False

    def test_missing_value_blocks_only_authoritative_sources(self):
        assert metadata_gate_unverifiable(None, best_effort=False) is True
        assert metadata_gate_unverifiable(None, best_effort=True) is False


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

    async def test_twitch_vod_url(self):
        resolved = await resolve_video_url("https://www.twitch.tv/videos/123456789")
        assert resolved == ResolvedVideo(video_type="twitch_vod", video_id="123456789")

    async def test_twitch_vod_url_with_timestamp(self):
        resolved = await resolve_video_url("https://www.twitch.tv/videos/123?t=1h2m3s")
        assert resolved == ResolvedVideo(
            video_type="twitch_vod", video_id="123", start_seconds=3723
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

    async def test_instagram_reel_url(self):
        resolved = await resolve_video_url("https://www.instagram.com/reel/Cabc123/")
        assert resolved == ResolvedVideo(video_type="instagram_reel", video_id="Cabc123")

    async def test_instagram_share_link_resolves_via_redirect(self):
        with patch(
            "shared.video_sources.resolve_instagram_url", new=AsyncMock(return_value="Cabc123")
        ):
            resolved = await resolve_video_url("https://www.instagram.com/share/xyz")
        assert resolved == ResolvedVideo(video_type="instagram_reel", video_id="Cabc123")

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
            new=AsyncMock(
                return_value=YouTubeInfo(
                    title="Title", duration_seconds=120, view_count=1000, is_vertical=False
                )
            ),
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
            new=AsyncMock(
                return_value=YouTubeInfo(
                    title="Title", duration_seconds=60, view_count=500, is_vertical=False
                )
            ),
        ):
            metadata = await fetch_video_metadata(resolved, youtube_api_key="key")
        assert metadata.is_vertical is True

    async def test_youtube_unplayable_reason_propagates(self):
        resolved = ResolvedVideo(video_type="youtube", video_id="dQw4w9WgXcQ")
        with patch(
            "shared.video_sources.fetch_yt_info",
            new=AsyncMock(
                return_value=YouTubeInfo(
                    title="Restricted", playable=False, unplayable_reason="age_restricted"
                )
            ),
        ):
            metadata = await fetch_video_metadata(resolved, youtube_api_key="key")
        assert metadata.playable is False
        assert metadata.unplayable_reason == "age_restricted"

    async def test_twitch_clip_and_bilibili_always_playable(self):
        clip = ResolvedVideo(video_type="twitch_clip", video_id="Slug")
        with patch(
            "shared.video_sources.fetch_twitch_clip_info",
            new=AsyncMock(return_value=("Clip", 30, 200, None)),
        ):
            metadata = await fetch_video_metadata(
                clip, twitch_client_id="c", twitch_client_secret="s"
            )
        assert metadata.playable is True
        assert metadata.unplayable_reason is None

    async def test_twitch_clip_normalizes_to_video_metadata(self):
        resolved = ResolvedVideo(video_type="twitch_clip", video_id="SomeClipSlug")
        with patch(
            "shared.video_sources.fetch_twitch_clip_info",
            new=AsyncMock(return_value=("Clip Title", 30, 200, "https://clips-media/x.jpg")),
        ) as mock_fetch:
            metadata = await fetch_video_metadata(
                resolved, twitch_client_id="cid", twitch_client_secret="secret"
            )
        mock_fetch.assert_awaited_once_with("SomeClipSlug", "cid", "secret", None)
        assert metadata == VideoMetadata(
            title="Clip Title",
            duration_seconds=30,
            view_count=200,
            is_vertical=False,
            thumbnail_url="https://clips-media/x.jpg",
        )

    async def test_twitch_vod_caps_the_play_window_from_the_offset(self):
        # 2h VOD, start 1h50m in → 10min remains, capped at the 600s window.
        resolved = ResolvedVideo(video_type="twitch_vod", video_id="123", start_seconds=6600)
        with patch(
            "shared.video_sources.fetch_twitch_vod_info",
            new=AsyncMock(
                return_value=("VOD Title", 7200, 5000, "https://static-cdn.jtvnw.net/t.jpg")
            ),
        ):
            metadata = await fetch_video_metadata(
                resolved, twitch_client_id="c", twitch_client_secret="s"
            )
        assert metadata == VideoMetadata(
            title="VOD Title",
            duration_seconds=600,
            view_count=5000,
            is_vertical=False,
            thumbnail_url="https://static-cdn.jtvnw.net/t.jpg",
        )

    async def test_twitch_vod_shorter_remainder_wins_over_the_cap(self):
        resolved = ResolvedVideo(video_type="twitch_vod", video_id="123", start_seconds=7100)
        with patch(
            "shared.video_sources.fetch_twitch_vod_info",
            new=AsyncMock(return_value=("VOD", 7200, 1, None)),
        ):
            metadata = await fetch_video_metadata(
                resolved, twitch_client_id="c", twitch_client_secret="s"
            )
        assert metadata.duration_seconds == 100

    async def test_twitch_vod_unknown_duration_falls_back_to_the_window(self):
        resolved = ResolvedVideo(video_type="twitch_vod", video_id="123")
        with patch(
            "shared.video_sources.fetch_twitch_vod_info",
            new=AsyncMock(return_value=(None, None, None, None)),
        ):
            metadata = await fetch_video_metadata(
                resolved, twitch_client_id="c", twitch_client_secret="s"
            )
        assert metadata.duration_seconds == 600

    async def test_bilibili_delegates_and_preserves_shape(self):
        resolved = ResolvedVideo(video_type="bilibili", video_id="BV1xx411c7mD")
        with patch(
            "shared.video_sources.fetch_bilibili_info",
            new=AsyncMock(return_value=("BV Title", 90, 5000, True, "https://i0.hdslb.com/x.jpg")),
        ) as mock_fetch:
            metadata = await fetch_video_metadata(resolved)
        mock_fetch.assert_awaited_once_with("BV1xx411c7mD", None)
        assert metadata == VideoMetadata(
            title="BV Title",
            duration_seconds=90,
            view_count=5000,
            is_vertical=True,
            metadata_best_effort=True,
            thumbnail_url="https://i0.hdslb.com/x.jpg",
        )

    async def test_bilibili_flags_best_effort_even_when_the_endpoint_fails(self):
        # 412 risk-control → all-None; the flag must still be set so submission
        # gates skip rather than reject a video that can never satisfy them.
        resolved = ResolvedVideo(video_type="bilibili", video_id="BV1FjxHzGEkQ")
        with patch(
            "shared.video_sources.fetch_bilibili_info",
            new=AsyncMock(return_value=(None, None, None, False, None)),
        ):
            metadata = await fetch_video_metadata(resolved)
        assert metadata.metadata_best_effort is True
        assert metadata.duration_seconds is None

    async def test_instagram_reel_delegates_and_preserves_shape(self):
        # duration_seconds now rides along in the same video-redirect fetch
        # that resolves the play-time mp4 URL (see shared.instafix_client's
        # _extract_duration_seconds) — no longer permanently None like
        # view_count.
        resolved = ResolvedVideo(video_type="instagram_reel", video_id="Cabc123")
        with patch(
            "shared.video_sources.fetch_instagram_reel_info",
            new=AsyncMock(
                return_value=InstagramReelInfo(
                    title="Alice",
                    thumbnail_url="https://cdn.example/thumb.jpg",
                    duration_seconds=16,
                )
            ),
        ) as mock_fetch:
            metadata = await fetch_video_metadata(resolved, instafix_host="instafix:3000")
        mock_fetch.assert_awaited_once_with("Cabc123", "instafix:3000", None)
        assert metadata == VideoMetadata(
            title="Alice",
            duration_seconds=16,
            view_count=None,
            # Every Reel is 9:16 — always True, unlike YouTube where only
            # Shorts are vertical — so the overlay gives it the same
            # blurred-side-column treatment.
            is_vertical=True,
            metadata_best_effort=True,
            thumbnail_url="https://cdn.example/thumb.jpg",
        )

    async def test_instagram_reel_always_best_effort_even_when_resolve_fails(self):
        # view_count has no field in InstaFix's OG data at all — unlike
        # Bilibili's -412, this is permanent, not transient, so the flag
        # must be set even on a "successful" (all-None) fetch. duration_seconds
        # can independently be None too (e.g. the video-redirect fetch failed).
        resolved = ResolvedVideo(video_type="instagram_reel", video_id="Cabc123")
        with patch(
            "shared.video_sources.fetch_instagram_reel_info",
            new=AsyncMock(
                return_value=InstagramReelInfo(
                    title=None, thumbnail_url=None, duration_seconds=None
                )
            ),
        ):
            metadata = await fetch_video_metadata(resolved)
        assert metadata.metadata_best_effort is True
        assert metadata.duration_seconds is None
        assert metadata.view_count is None
        assert metadata.playable is True
        assert metadata.is_vertical is True

    async def test_authoritative_platforms_are_not_best_effort(self):
        yt = ResolvedVideo(video_type="youtube", video_id="dQw4w9WgXcQ")
        with patch(
            "shared.video_sources.fetch_yt_info",
            new=AsyncMock(return_value=YouTubeInfo(title="T", duration_seconds=1, view_count=1)),
        ):
            assert (
                await fetch_video_metadata(yt, youtube_api_key="k")
            ).metadata_best_effort is False
        clip = ResolvedVideo(video_type="twitch_clip", video_id="Slug")
        with patch(
            "shared.video_sources.fetch_twitch_clip_info",
            new=AsyncMock(return_value=("C", 30, 200, None)),
        ):
            meta = await fetch_video_metadata(clip, twitch_client_id="c", twitch_client_secret="s")
        assert meta.metadata_best_effort is False

    async def test_fetch_failure_propagates_all_none(self):
        resolved = ResolvedVideo(video_type="youtube", video_id="dQw4w9WgXcQ")
        with patch(
            "shared.video_sources.fetch_yt_info",
            new=AsyncMock(return_value=YouTubeInfo()),
        ):
            metadata = await fetch_video_metadata(resolved, youtube_api_key="key")
        assert metadata == VideoMetadata(
            title=None, duration_seconds=None, view_count=None, is_vertical=False
        )
        # A failed fetch is fail-open: never rejects a submission.
        assert metadata.playable is True


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

    def test_twitch_vod(self):
        assert (
            build_watch_url("twitch_vod", "123456789") == "https://www.twitch.tv/videos/123456789"
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
