"""Data models for stream analytics tables."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class StreamSession:
    """A single stream session record."""

    id: int
    channel_id: str
    started_at: datetime
    ended_at: datetime | None = None
    title: str | None = None
    game_name: str | None = None
    game_id: str | None = None
    created_at: datetime | None = None


@dataclass
class CommandStat:
    """Per-session per-command aggregated usage."""

    id: int
    session_id: int
    channel_id: str
    command_name: str
    usage_count: int = 1
    last_used_at: datetime | None = None
    created_at: datetime | None = None


@dataclass
class StreamEvent:
    """Stream event record (follow / subscribe / raid)."""

    id: int
    session_id: int
    channel_id: str
    event_type: str
    user_id: str | None = None
    username: str | None = None
    display_name: str | None = None
    metadata: dict | None = field(default=None)
    occurred_at: datetime | None = None
    created_at: datetime | None = None
