"""Data models for Discord birthday feature tables."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class Birthday:
    """User birthday data."""

    user_id: int
    month: int
    day: int
    year: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class BirthdaySettings:
    """Guild-level birthday notification settings."""

    guild_id: int
    channel_id: int
    role_id: int
    message_template: str = "今天是 {users} 的生日，請各位送上祝福！"
    last_notified_date: date | None = None
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
