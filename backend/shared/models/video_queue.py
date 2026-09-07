"""Data models for video_queue and video_queue_settings tables."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class VideoQueueEntry:
    """Video queue entry record."""

    id: int
    channel_id: str
    video_id: str
    requested_by: str
    source: str  # 'chat' | 'redemption' | 'donation' | 'dashboard'
    status: str  # 'queued' | 'playing' | 'done' | 'skipped'
    video_type: str = "youtube"  # 'youtube' | 'twitch_clip' | 'bilibili'
    priority: int = 0
    title: str | None = None
    duration_seconds: int | None = None
    is_vertical: bool = False
    created_at: datetime | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None  # set when status moves to done/skipped
    requested_by_id: str | None = None  # Twitch user ID; None for legacy rows


@dataclass
class VideoQueueSettings:
    """Video queue settings record."""

    channel_id: str
    enabled: bool = True
    redemption_enabled: bool = True
    max_duration_redemption: int = 600  # redemption source limit (10 min)
    max_queue_size: int = 20
    min_view_count: int = 0  # 0 = no restriction
    user_cooldown_seconds: int = 0  # 0 = no restriction
    max_per_user: int = 0  # 0 = no restriction
    created_at: datetime | None = None
    updated_at: datetime | None = None
