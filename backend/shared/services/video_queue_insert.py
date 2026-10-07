"""Live insert (直播插播): validate a live URL and start/stop the insert.

A live insert is the broadcaster playing someone's ongoing live stream in the
overlay — background music, a watch-along — until they stop it or the stream
ends. It is not a queue entry (no length, no review, no place in line), so it
never goes through VideoQueueAdmissionService; only the broadcaster can start
one (chat `!vq live` or the dashboard). See migration 155 and
tasks/video-queue-live-and-segments.md (情境 2).

Fetchers are injected, same as admission, so the Twitch bot can reuse its
aiohttp session.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

from shared.models.video_queue import VideoQueueInsert
from shared.repositories.video_queue import (
    VideoQueueInsertRepository,
    VideoQueueSettingsRepository,
)
from shared.video_sources import (
    UNPLAYABLE_LIVE,
    TwitchLiveLookupError,
    TwitchLiveStream,
    YouTubeInfo,
    extract_twitch_channel_login,
    extract_youtube_id,
)

FetchYouTube = Callable[[str], Awaitable[YouTubeInfo]]
FetchTwitchLive = Callable[[str], Awaitable[TwitchLiveStream | None]]


class InsertReason(StrEnum):
    INVALID_URL = "invalid_url"
    NOT_LIVE = "not_live"
    OWN_CHANNEL = "own_channel"
    NOT_PLAYABLE = "not_playable"
    UNVERIFIABLE = "unverifiable"


class InsertRejected(Exception):  # noqa: N818 - domain outcome, not an internal error
    def __init__(self, reason: InsertReason, *, unplayable_reason: str | None = None) -> None:
        self.reason = reason
        self.unplayable_reason = unplayable_reason
        super().__init__(reason.value)


@dataclass(frozen=True)
class LiveSource:
    source_type: str  # 'twitch_live' | 'youtube_live'
    source_id: str
    title: str | None
    creator_id: str | None
    creator_name: str | None
    thumbnail_url: str | None


async def resolve_live_source(
    url: str,
    *,
    own_channel_id: str,
    fetch_youtube: FetchYouTube,
    fetch_twitch_live: FetchTwitchLive,
) -> LiveSource:
    """Identify an ongoing live stream from ``url`` or raise ``InsertRejected``."""
    video_id = extract_youtube_id(url)
    if video_id:
        info = await fetch_youtube(video_id)
        if info.live_status is None:
            # Nothing came back: API failure, or the video doesn't exist.
            raise InsertRejected(InsertReason.UNVERIFIABLE)
        if info.unplayable_reason not in (None, UNPLAYABLE_LIVE):
            raise InsertRejected(
                InsertReason.NOT_PLAYABLE, unplayable_reason=info.unplayable_reason
            )
        if info.live_status != "live":  # 'upcoming' or an ordinary video
            raise InsertRejected(InsertReason.NOT_LIVE)
        return LiveSource(
            source_type="youtube_live",
            source_id=video_id,
            title=info.title,
            creator_id=info.creator_id,
            creator_name=info.creator_name,
            thumbnail_url=info.thumbnail_url,
        )

    login = extract_twitch_channel_login(url)
    if login:
        try:
            stream = await fetch_twitch_live(login)
        except TwitchLiveLookupError as error:
            raise InsertRejected(InsertReason.UNVERIFIABLE) from error
        if stream is None:
            raise InsertRejected(InsertReason.NOT_LIVE)
        # Playing your own live stream mirrors the picture and feeds the audio back.
        if stream.user_id == own_channel_id:
            raise InsertRejected(InsertReason.OWN_CHANNEL)
        return LiveSource(
            source_type="twitch_live",
            source_id=stream.user_login,
            title=stream.title,
            creator_id=stream.user_id,
            creator_name=stream.user_name,
            thumbnail_url=stream.thumbnail_url,
        )

    raise InsertRejected(InsertReason.INVALID_URL)


class VideoQueueInsertService:
    def __init__(
        self, inserts: VideoQueueInsertRepository, settings: VideoQueueSettingsRepository
    ) -> None:
        self.inserts = inserts
        self.settings = settings

    async def start(
        self,
        *,
        channel_id: str,
        url: str,
        fetch_youtube: FetchYouTube,
        fetch_twitch_live: FetchTwitchLive,
    ) -> VideoQueueInsert:
        source = await resolve_live_source(
            url,
            own_channel_id=channel_id,
            fetch_youtube=fetch_youtube,
            fetch_twitch_live=fetch_twitch_live,
        )
        settings = await self.settings.get_or_create(channel_id)
        return await self.inserts.start(
            channel_id,
            source_type=source.source_type,
            source_id=source.source_id,
            title=source.title,
            creator_id=source.creator_id,
            creator_name=source.creator_name,
            thumbnail_url=source.thumbnail_url,
            volume_percent=settings.insert_volume_percent,
            audio_only=settings.insert_audio_only,
        )
