"""Data model for event_configs table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class EventConfig:
    """Event configuration record."""

    id: int
    channel_id: str
    event_type: str  # 'follow' | 'subscribe' | 'raid'
    message_template: str
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
