"""Data model for event_configs table."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from shared.events import EventKey


@dataclass
class EventConfig:
    """Event configuration record."""

    id: int
    channel_id: str
    event_type: EventKey  # see shared.events.EVENT_CATALOG
    message_template: str
    enabled: bool = True
    # per-event JSONB; shapes: raid {"auto_shoutout": bool}, bits {"tiers": [...]}
    options: dict = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
