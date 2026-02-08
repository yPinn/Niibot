"""Data models for command_configs and redemption_configs tables."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class CommandConfig:
    """Command configuration record (builtin + custom unified)."""

    id: int
    channel_id: str
    command_name: str
    command_type: str = "builtin"  # 'builtin' | 'custom'
    enabled: bool = True
    custom_response: str | None = None
    redirect_to: str | None = None
    cooldown_global: int = 0
    cooldown_per_user: int = 0
    min_role: str = "everyone"  # 'everyone' | 'subscriber' | 'vip' | 'moderator' | 'broadcaster'
    aliases: str | None = None  # Comma-separated alias names, e.g. "hello,嗨"
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class RedemptionConfig:
    """Redemption configuration record."""

    id: int
    channel_id: str
    action_type: str  # 'vip' | 'first' | 'niibot_auth'
    reward_name: str
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
