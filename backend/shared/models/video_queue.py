"""Data models for video_queue and video_queue_settings tables."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4


@dataclass
class VideoQueueEntry:
    """Video queue entry record."""

    id: int
    channel_id: str
    video_id: str
    requested_by: str
    source: str  # 'chat' | 'redemption' | 'donation' | 'dashboard'
    status: str  # 'queued' | 'playing' | 'done' | 'skipped'
    video_type: str = (
        "youtube"  # 'youtube' | 'twitch_clip' | 'twitch_vod' | 'bilibili' | 'instagram_reel'
    )
    priority: int = 0
    title: str | None = None
    duration_seconds: int | None = None  # for twitch_vod: the capped play window
    is_vertical: bool = False
    thumbnail_url: str | None = None  # poster/cover image; None → card placeholder
    start_seconds: int = 0  # twitch_vod: seek offset from the URL's `?t=`
    created_at: datetime | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None  # set when status moves to done/skipped
    requested_by_id: str | None = None  # Twitch user ID; None for legacy rows
    creator_id: str | None = None  # platform-native id of who made the content
    creator_name: str | None = None  # display label; not matched against, cosmetic only
    # Playback facts are separate from queue state. ``started_at`` means the
    # row was promoted; this timestamp means a player actually attempted or
    # confirmed playback and is therefore eligible for rankings.
    playback_started_at: datetime | None = None
    playback_signal: str | None = None  # 'confirmed' | 'best_effort'
    end_reason: str | None = None
    played_seconds: int | None = None


@dataclass
class VideoQueueBlocklistEntry:
    """One Video Queue blocklist rule (see migration 110)."""

    id: int
    channel_id: str
    kind: str  # 'video' | 'creator' | 'keyword' | 'user'
    value: str  # what a submission is matched against (case-insensitive)
    # Only video/creator rules may be provider-scoped. None is a legacy or
    # manually-created wildcard which intentionally applies to every provider.
    video_type: str | None = None
    label: str | None = None  # human note for the dashboard list
    created_by: str | None = None
    created_at: datetime | None = None


@dataclass
class VideoQueueRankingEntry:
    """Anonymous aggregate used by the private ranking workbench."""

    rank: int
    video_type: str
    video_id: str
    start_seconds: int
    title: str | None
    thumbnail_url: str | None
    creator_id: str | None
    creator_name: str | None
    play_count: int
    channel_count: int
    last_played_at: datetime
    active_status: str | None = None
    blocked_kind: str | None = None


@dataclass
class VideoQueueSettings:
    """Video queue settings record."""

    channel_id: str
    overlay_key: UUID = field(default_factory=uuid4)
    enabled: bool = True
    redemption_enabled: bool = True
    max_duration_redemption: int = 600  # redemption source limit (10 min)
    max_queue_size: int = 20
    min_view_count: int = 0  # 0 = no restriction
    user_cooldown_seconds: int = 0  # 0 = no restriction
    max_per_user: int = 0  # 0 = no restriction
    max_duration_seconds: int = 0  # global length cap for every source; 0 = no limit
    replay_cooldown_hours: int = 0  # reject a video played within N hours; 0 = no limit
    # Normalized output gain where the provider exposes volume control; shared
    # by queue videos and live streams (migration 157).
    volume_percent: int = 50
    insert_audio_only: bool = False  # default: a live insert plays without its picture
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class VideoQueueInsert:
    """An active live insert (直播播放) — see migration 155.

    Broadcaster-only, open-ended playback of an ongoing live stream; not a
    queue entry. ``source_id`` is the Twitch channel login or the YouTube
    video id of the live broadcast.
    """

    id: int
    channel_id: str
    source_type: str  # 'twitch_live' | 'youtube_live'
    source_id: str
    volume_percent: int
    audio_only: bool = False
    title: str | None = None
    creator_id: str | None = None
    creator_name: str | None = None
    thumbnail_url: str | None = None
    started_at: datetime | None = None
