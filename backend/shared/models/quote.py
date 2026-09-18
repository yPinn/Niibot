"""Quote model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Quote:
    id: int
    channel_id: str
    quote_number: int
    quote_text: str
    created_by: str
    created_at: datetime | None = None
