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
    BilibiliInfo,
    ResolvedVideo,
    TwitchMediaInfo,
    VideoMetadata,
    YouTubeInfo,
    build_watch_url,
    fetch_video_metadata,
    is_twitch_channel_url,
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

    @pytest.mark.parametrize(
        "url",
        [
            "https://youtu.be/dQw4w9WgXcQ?t=90",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=1m30s",
            "https://www.youtube.com/embed/dQw4w9WgXcQ?start=45",
        ],
    )
    async def test_youtube_url_offset_is_ignored(self, url):
        # YouTube appends the viewer's own resume position to copied URLs —
        # not a start point the requester chose.
        resolved = await resolve_video_url(url)
        assert resolved is not None
        assert resolved.start_seconds == 0

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

    async def test_youtube_live_url(self):
        resolved = await resolve_video_url("https://www.youtube.com/live/dQw4w9WgXcQ")
        assert resolved == ResolvedVideo(video_type="youtube", video_id="dQw4w9WgXcQ")

    async def test_twitch_mobile_clip_url(self):
        resolved = await resolve_video_url("https://m.twitch.tv/streamer/clip/SomeClipSlug")
        assert resolved == ResolvedVideo(video_type="twitch_clip", video_id="SomeClipSlug")

    async def test_bilibili_page_2_folded_into_video_id(self):
        resolved = await resolve_video_url("https://www.bilibili.com/video/BV1xx411c7mD?p=2")
        assert resolved == ResolvedVideo(
            video_type="bilibili", video_id="BV1xx411c7mD_p2", is_vertical=False
        )

    async def test_instagram_p_url(self):
        resolved = await resolve_video_url("https://www.instagram.com/p/Cabc123/")
        assert resolved == ResolvedVideo(video_type="instagram_reel", video_id="Cabc123")

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=abc123&utm_source=share",
            "https://www.bilibili.com/video/BV1xx411c7mD?spm_id_from=333.999&vd_source=abc",
            "https://www.instagram.com/reel/Cabc123/?igsh=xyz789",
        ],
    )
    async def test_tracking_params_do_not_affect_resolution(self, url):
        # utm_*/si/spm_id_from/vd_source/igsh are share-tracking noise — only the
        # native id is ever extracted, so a tracking-laden URL and a clean one
        # for the same video resolve to the same id.
        resolved = await resolve_video_url(url)
        assert resolved is not None
        assert resolved.video_id in {"dQw4w9WgXcQ", "BV1xx411c7mD", "Cabc123"}


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
            new=AsyncMock(
                return_value=TwitchMediaInfo(title="Clip", duration_seconds=30, view_count=200)
            ),
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
            new=AsyncMock(
                return_value=TwitchMediaInfo(
                    title="Clip Title",
                    duration_seconds=30,
                    view_count=200,
                    thumbnail_url="https://clips-media/x.jpg",
                    creator_id="b123",
                    creator_name="SomeBroadcaster",
                )
            ),
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
            creator_id="b123",
            creator_name="SomeBroadcaster",
        )

    async def test_twitch_vod_reports_the_full_length(self):
        # The play window is resolved at admission (shared.video_segments).
        resolved = ResolvedVideo(video_type="twitch_vod", video_id="123", start_seconds=6600)
        with patch(
            "shared.video_sources.fetch_twitch_vod_info",
            new=AsyncMock(
                return_value=TwitchMediaInfo(
                    title="VOD Title",
                    duration_seconds=7200,
                    view_count=5000,
                    thumbnail_url="https://static-cdn.jtvnw.net/t.jpg",
                )
            ),
        ):
            metadata = await fetch_video_metadata(
                resolved, twitch_client_id="c", twitch_client_secret="s"
            )
        assert metadata == VideoMetadata(
            title="VOD Title",
            duration_seconds=7200,
            view_count=5000,
            is_vertical=False,
            thumbnail_url="https://static-cdn.jtvnw.net/t.jpg",
        )

    async def test_bilibili_delegates_and_preserves_shape(self):
        resolved = ResolvedVideo(video_type="bilibili", video_id="BV1xx411c7mD")
        with patch(
            "shared.video_sources.fetch_bilibili_info",
            new=AsyncMock(
                return_value=BilibiliInfo(
                    title="BV Title",
                    duration_seconds=90,
                    view_count=5000,
                    is_vertical=True,
                    thumbnail_url="https://i0.hdslb.com/x.jpg",
                    creator_id="12345",
                    creator_name="SomeUploader",
                )
            ),
        ) as mock_fetch:
            metadata = await fetch_video_metadata(resolved)
        mock_fetch.assert_awaited_once_with("BV1xx411c7mD", None, page=1)
        assert metadata == VideoMetadata(
            title="BV Title",
            duration_seconds=90,
            view_count=5000,
            is_vertical=True,
            metadata_best_effort=True,
            thumbnail_url="https://i0.hdslb.com/x.jpg",
            creator_id="12345",
            creator_name="SomeUploader",
        )

    async def test_bilibili_flags_best_effort_even_when_the_endpoint_fails(self):
        # 412 risk-control → all-None; the flag must still be set so submission
        # gates skip rather than reject a video that can never satisfy them.
        resolved = ResolvedVideo(video_type="bilibili", video_id="BV1FjxHzGEkQ")
        with patch(
            "shared.video_sources.fetch_bilibili_info",
            new=AsyncMock(return_value=BilibiliInfo()),
        ):
            metadata = await fetch_video_metadata(resolved)
        assert metadata.metadata_best_effort is True
        assert metadata.duration_seconds is None

    async def test_bilibili_page_2_splits_id_and_forwards_page(self):
        resolved = ResolvedVideo(video_type="bilibili", video_id="BV1xx411c7mD_p2")
        with patch(
            "shared.video_sources.fetch_bilibili_info",
            new=AsyncMock(
                return_value=BilibiliInfo(
                    title="Collection P2 Part Two",
                    duration_seconds=200,
                    view_count=10,
                    page_count=3,
                )
            ),
        ) as mock_fetch:
            metadata = await fetch_video_metadata(resolved)
        mock_fetch.assert_awaited_once_with("BV1xx411c7mD", None, page=2)
        assert metadata.title == "Collection P2 Part Two"
        assert metadata.duration_seconds == 200
        assert metadata.playable is True

    async def test_bilibili_page_past_the_end_is_rejected(self):
        # page_count is only known when the view endpoint actually answered —
        # rejecting requires that positive signal, not just "duration missing".
        resolved = ResolvedVideo(video_type="bilibili", video_id="BV1xx411c7mD_p9")
        with patch(
            "shared.video_sources.fetch_bilibili_info",
            new=AsyncMock(return_value=BilibiliInfo(title="Collection", page_count=3)),
        ):
            metadata = await fetch_video_metadata(resolved)
        assert metadata.playable is False
        assert metadata.unplayable_reason == "invalid_page"
        assert metadata.duration_seconds == 0

    async def test_bilibili_page_past_the_end_not_rejected_when_page_count_unknown(self):
        # A -412 risk-control miss returns page_count=None — must not reject a
        # part number we simply couldn't verify.
        resolved = ResolvedVideo(video_type="bilibili", video_id="BV1xx411c7mD_p9")
        with patch(
            "shared.video_sources.fetch_bilibili_info",
            new=AsyncMock(return_value=BilibiliInfo()),
        ):
            metadata = await fetch_video_metadata(resolved)
        assert metadata.playable is True

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
            # InstagramReelInfo.is_vertical defaults True — this test's
            # fixture doesn't set it explicitly (see test_instafix_client.py
            # for the OG-dimension detection itself).
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

    async def test_instagram_photo_post_rejected_as_not_video(self):
        # A `/p/` link that resolved to a photo post — is_video is positively
        # False (the /videos/ redirect resolved to a non-mp4 target), not
        # merely unknown, so this is the one case that rejects.
        resolved = ResolvedVideo(video_type="instagram_reel", video_id="Cabc123")
        with patch(
            "shared.video_sources.fetch_instagram_reel_info",
            new=AsyncMock(
                return_value=InstagramReelInfo(
                    title="A photo caption",
                    thumbnail_url=None,
                    duration_seconds=None,
                    is_video=False,
                )
            ),
        ):
            metadata = await fetch_video_metadata(resolved)
        assert metadata.playable is False
        assert metadata.unplayable_reason == "not_video"

    async def test_instagram_unknown_video_status_not_rejected(self):
        # The /videos/ redirect merely failed to resolve (network hiccup) —
        # is_video stays None/unknown, and that must not reject the submission.
        resolved = ResolvedVideo(video_type="instagram_reel", video_id="Cabc123")
        with patch(
            "shared.video_sources.fetch_instagram_reel_info",
            new=AsyncMock(
                return_value=InstagramReelInfo(
                    title="A reel", thumbnail_url=None, duration_seconds=None, is_video=None
                )
            ),
        ):
            metadata = await fetch_video_metadata(resolved)
        assert metadata.playable is True

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
            new=AsyncMock(
                return_value=TwitchMediaInfo(title="C", duration_seconds=30, view_count=200)
            ),
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

    def test_bilibili_multi_part(self):
        assert (
            build_watch_url("bilibili", "BV1xx411c7mD_p2")
            == "https://www.bilibili.com/video/BV1xx411c7mD?p=2"
        )

    def test_start_offset_is_carried_for_seekable_platforms(self):
        assert build_watch_url("youtube", "dQw4w9WgXcQ", 90) == "https://youtu.be/dQw4w9WgXcQ?t=90"
        assert build_watch_url("twitch_vod", "123", 90) == "https://www.twitch.tv/videos/123?t=90s"
        assert (
            build_watch_url("bilibili", "BV1xx411c7mD_p2", 90)
            == "https://www.bilibili.com/video/BV1xx411c7mD?p=2&t=90"
        )
        assert build_watch_url("twitch_clip", "Slug", 90) == "https://clips.twitch.tv/Slug"

    def test_unknown_video_type_raises(self):
        with pytest.raises(ValueError, match="Unknown video_type"):
            build_watch_url("tiktok", "abc123")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("https://www.twitch.tv/somestreamer", True),
        ("twitch.tv/some_streamer/", True),
        ("https://www.twitch.tv/videos/123", False),
        ("https://www.twitch.tv/directory", False),
        ("https://clips.twitch.tv/SomeClip", False),
        ("https://youtu.be/dQw4w9WgXcQ", False),
    ],
)
def test_is_twitch_channel_url(text, expected):
    assert is_twitch_channel_url(text) is expected


@pytest.mark.asyncio
class TestFetchTwitchLiveStream:
    async def _fetch(self, helix_result):
        from shared.video_sources import fetch_twitch_live_stream

        with (
            patch("shared.video_sources._get_twitch_app_token", AsyncMock(return_value="tok")),
            patch("shared.video_sources._twitch_helix_json", AsyncMock(return_value=helix_result)),
        ):
            return await fetch_twitch_live_stream("lofistreamer", "c", "s", session=AsyncMock())

    async def test_live(self):
        stream = await self._fetch(
            (
                200,
                {
                    "data": [
                        {
                            "type": "live",
                            "user_id": "u-9",
                            "user_login": "lofistreamer",
                            "user_name": "LofiStreamer",
                            "title": "beats",
                            "thumbnail_url": "https://t/{width}x{height}.jpg",
                        }
                    ]
                },
            )
        )
        assert stream is not None
        assert (stream.user_id, stream.user_name, stream.title) == ("u-9", "LofiStreamer", "beats")
        assert stream.thumbnail_url == "https://t/320x180.jpg"

    async def test_offline(self):
        assert await self._fetch((200, {"data": []})) is None

    async def test_http_failure_is_not_offline(self):
        from shared.video_sources import TwitchLiveLookupError

        with pytest.raises(TwitchLiveLookupError):
            await self._fetch((500, {}))

    async def test_missing_credentials_is_not_offline(self):
        from shared.video_sources import TwitchLiveLookupError, fetch_twitch_live_stream

        with pytest.raises(TwitchLiveLookupError):
            await fetch_twitch_live_stream("lofistreamer", "", "")


class _GqlResponse:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def json(self, content_type=None):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


def _gql_session(status, payload):
    from unittest.mock import MagicMock

    session = MagicMock()
    session.post = MagicMock(return_value=_GqlResponse(status, payload))
    return session


@pytest.mark.asyncio
class TestFetchTwitchLiveHlsSource:
    async def test_builds_a_signed_usher_playlist_url(self):
        from urllib.parse import parse_qs, urlsplit

        from shared.video_sources import fetch_twitch_live_hls_source

        token = {"value": '{"channel":"lofi"}', "signature": "abc123", "authorization": {}}
        session = _gql_session(200, {"data": {"streamPlaybackAccessToken": token}})
        url = await fetch_twitch_live_hls_source("lofi", session)
        assert url is not None
        parts = urlsplit(url)
        assert parts.netloc == "usher.ttvnw.net"
        assert parts.path == "/api/channel/hls/lofi.m3u8"
        query = parse_qs(parts.query)
        assert query["sig"] == ["abc123"]
        assert query["token"] == ['{"channel":"lofi"}']
        assert query["supported_codecs"] == ["avc1"]
        sent = session.post.call_args.kwargs
        assert "PlaybackAccessToken_Template" in sent["data"]

    @pytest.mark.parametrize(
        ("status", "payload"),
        [
            (500, {}),
            (200, {"data": {"streamPlaybackAccessToken": None}}),
            (
                200,
                {
                    "data": {
                        "streamPlaybackAccessToken": {
                            "value": "v",
                            "signature": "s",
                            "authorization": {"isForbidden": True},
                        }
                    }
                },
            ),
        ],
    )
    async def test_failures_return_none(self, status, payload):
        from shared.video_sources import fetch_twitch_live_hls_source

        assert await fetch_twitch_live_hls_source("lofi", _gql_session(status, payload)) is None


class _TextResponse:
    def __init__(self, status, text):
        self.status = status
        self._text = text

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "text", "expected"),
    [
        (200, "#EXTM3U\nhttps://x/v.m3u8\n", "#EXTM3U\nhttps://x/v.m3u8\n"),
        (404, "#EXTM3U\n", None),
        (200, "<html>blocked</html>", None),
    ],
)
async def test_fetch_hls_master_playlist(status, text, expected):
    from unittest.mock import MagicMock

    from shared.video_sources import fetch_hls_master_playlist

    session = MagicMock()
    session.get = MagicMock(return_value=_TextResponse(status, text))
    assert await fetch_hls_master_playlist("https://usher.ttvnw.net/x.m3u8", session) == expected
