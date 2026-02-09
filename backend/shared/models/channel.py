"""Data models for Twitch channel, token, and Discord user tables."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Token:
    """OAuth token record."""

    user_id: str
    token: str
    refresh: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Channel:
    """Twitch channel record."""

    channel_id: str
    channel_name: str
    enabled: bool = True
    default_cooldown: int = 5
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class DiscordUser:
    """Cached Discord OAuth user info."""

    user_id: str
    username: str
    display_name: str | None = None
    avatar: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
