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
    source: str  # 'chat' | 'redemption'
    status: str  # 'queued' | 'playing' | 'done' | 'skipped'
    title: str | None = None
    duration_seconds: int | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


@dataclass
class VideoQueueSettings:
    """Video queue settings record."""

    channel_id: str
    enabled: bool = True
    min_role_chat: str = "everyone"
    max_duration_seconds: int = 600
    max_queue_size: int = 20
    created_at: datetime | None = None
    updated_at: datetime | None = None
