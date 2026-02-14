"""Data model for event_configs table."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EventConfig:
    """Event configuration record."""

    id: int
    channel_id: str
    event_type: str  # 'follow' | 'subscribe' | 'raid'
    message_template: str
    enabled: bool = True
    options: dict = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
