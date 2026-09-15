"""Data models for command_configs and redemption_configs tables."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class CommandConfig:
    """Command configuration record (builtin + custom unified)."""

    id: int | None
    channel_id: str
    command_name: str
    command_type: str = "builtin"  # 'builtin' | 'custom'
    enabled: bool = True
    custom_response: str | None = None
    cooldown: int | None = None  # NULL = use channel default
    min_role: str = "everyone"  # 'everyone' | 'subscriber' | 'vip' | 'moderator' | 'broadcaster'
    aliases: str | None = None  # Comma-separated alias names, e.g. "hello,嗨"
    usage_count: int = 0
    last_used_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class RedemptionConfig:
    """Redemption configuration record."""

    id: int
    channel_id: str
    action_type: str  # 'vip' | 'first' | 'niibot_auth' | 'game_queue' | 'video_queue' | 'checkin'
    reward_name: str
    reward_id: str | None = None
    enabled: bool = True
    first_message: str = "$(@user) 恭喜你搶到沙發！"
    first_announce_color: str = "primary"
    created_at: datetime | None = None
    updated_at: datetime | None = None
