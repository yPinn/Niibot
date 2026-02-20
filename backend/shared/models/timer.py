"""Timer config model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TimerConfig:
    id: int
    channel_id: str
    timer_name: str
    interval_seconds: int
    min_lines: int
    message_template: str
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
