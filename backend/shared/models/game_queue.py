"""Data models for game_queue_entries and game_queue_settings tables."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class GameQueueEntry:
    """Game queue entry record."""

    id: int
    channel_id: str
    user_id: str
    user_name: str
    redeemed_at: datetime
    removed_at: datetime | None = None
    removal_reason: str | None = None  # 'completed' | 'kicked' | 'cleared'
    created_at: datetime | None = None


@dataclass
class GameQueueSettings:
    """Game queue settings record."""

    id: int
    channel_id: str
    group_size: int = 4
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
