"""Live insert (直播播放) source validation — shared.services.video_queue_insert."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from shared.services.video_queue_insert import (
    InsertReason,
    InsertRejected,
    LiveSource,
    resolve_live_source,
)
from shared.video_sources import TwitchLiveLookupError, TwitchLiveStream, YouTubeInfo

OWN = "own-channel-id"


async def _resolve(url, *, youtube=None, twitch=None):
    return await resolve_live_source(
        url,
        own_channel_id=OWN,
        fetch_youtube=AsyncMock(return_value=youtube or YouTubeInfo()),
        fetch_twitch_live=twitch or AsyncMock(return_value=None),
    )


async def _rejected(url, **kw) -> InsertRejected:
    with pytest.raises(InsertRejected) as exc_info:
        await _resolve(url, **kw)
    return exc_info.value


@pytest.mark.asyncio
class TestYouTube:
    async def test_ongoing_live_is_accepted(self):
        info = YouTubeInfo(
            title="lofi radio",
            playable=False,
            unplayable_reason="live",
            creator_id="UC1",
            creator_name="Lofi Girl",
            live_status="live",
        )
        source = await _resolve("https://www.youtube.com/live/jfKfPfyJRdk", youtube=info)
        assert source == LiveSource(
            "youtube_live", "jfKfPfyJRdk", "lofi radio", "UC1", "Lofi Girl", None
        )

    async def test_upcoming_is_not_live(self):
        info = YouTubeInfo(title="x", live_status="upcoming")
        error = await _rejected("https://youtu.be/jfKfPfyJRdk", youtube=info)
        assert error.reason is InsertReason.NOT_LIVE

    async def test_regular_video_points_at_the_queue(self):
        info = YouTubeInfo(title="x", live_status="none")
        error = await _rejected("https://youtu.be/jfKfPfyJRdk", youtube=info)
        assert error.reason is InsertReason.IS_VIDEO

    async def test_not_embeddable_live_is_rejected(self):
        info = YouTubeInfo(
            title="x", playable=False, unplayable_reason="not_embeddable", live_status="live"
        )
        error = await _rejected("https://youtu.be/jfKfPfyJRdk", youtube=info)
        assert error.reason is InsertReason.NOT_PLAYABLE
        assert error.unplayable_reason == "not_embeddable"

    async def test_failed_lookup_is_unverifiable(self):
        error = await _rejected("https://youtu.be/jfKfPfyJRdk", youtube=YouTubeInfo())
        assert error.reason is InsertReason.UNVERIFIABLE


@pytest.mark.asyncio
class TestTwitch:
    async def test_live_channel_is_accepted(self):
        stream = TwitchLiveStream(
            "u-9", "lofistreamer", "LofiStreamer", "beats", "https://t/320x180.jpg"
        )
        twitch = AsyncMock(return_value=stream)
        source = await _resolve("twitch.tv/LofiStreamer", twitch=twitch)
        twitch.assert_awaited_once_with("lofistreamer")
        assert source == LiveSource(
            "twitch_live", "lofistreamer", "beats", "u-9", "LofiStreamer", "https://t/320x180.jpg"
        )

    async def test_offline_channel_is_rejected(self):
        error = await _rejected("https://www.twitch.tv/someone")
        assert error.reason is InsertReason.NOT_LIVE

    async def test_own_channel_is_rejected(self):
        stream = TwitchLiveStream(OWN, "itsme", "ItsMe")
        error = await _rejected(
            "https://www.twitch.tv/itsme", twitch=AsyncMock(return_value=stream)
        )
        assert error.reason is InsertReason.OWN_CHANNEL

    async def test_lookup_failure_is_not_reported_as_offline(self):
        twitch = AsyncMock(side_effect=TwitchLiveLookupError("status 500"))
        error = await _rejected("https://www.twitch.tv/someone", twitch=twitch)
        assert error.reason is InsertReason.UNVERIFIABLE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://www.twitch.tv/videos/123",
        "https://clips.twitch.tv/Slug",
        "https://www.bilibili.com/video/BV1xx411c7mD",
    ],
)
async def test_queueable_videos_point_at_the_queue(url):
    error = await _rejected(url)
    assert error.reason is InsertReason.IS_VIDEO


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["not a url", "https://example.com/watch"])
async def test_other_urls_are_invalid(url):
    error = await _rejected(url)
    assert error.reason is InsertReason.INVALID_URL
