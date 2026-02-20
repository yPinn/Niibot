"""Message trigger config model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class MessageTriggerConfig:
    id: int
    channel_id: str
    trigger_name: str
    match_type: str  # 'contains' | 'startswith' | 'exact' | 'regex'
    pattern: str
    case_sensitive: bool
    response: str
    min_role: str
    cooldown: int | None
    priority: int
    enabled: bool = True
    usage_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
