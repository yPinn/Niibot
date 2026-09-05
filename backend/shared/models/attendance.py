"""Typed records for daily check-ins and community overlay delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID


class CheckinStatus(StrEnum):
    RECORDED = "recorded"
    ALREADY_CHECKED_IN = "already_checked_in"


@dataclass(frozen=True, slots=True)
class CheckinSettings:
    channel_id: str
    timezone: str
    success_template: str
    duplicate_template: str
    reply_delay_seconds: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CheckinLeaderboardEntry:
    rank: int
    user_id: str
    username: str
    display_name: str | None
    total_days: int
    last_checkin_date: date


@dataclass(frozen=True, slots=True)
class CheckinRank:
    rank: int
    total_days: int
    last_checkin_date: date
    total_participants: int


@dataclass(frozen=True, slots=True)
class CheckinResult:
    status: CheckinStatus
    channel_id: str
    user_id: str
    username: str
    display_name: str | None
    checkin_date: date
    total_days: int
    checkin_id: int
    event_id: int | None
    occurred_at: datetime

    @property
    def recorded(self) -> bool:
        return self.status is CheckinStatus.RECORDED


@dataclass(frozen=True, slots=True)
class CheckinReply:
    result: CheckinResult
    message: str
    delay_seconds: int = 0


@dataclass(frozen=True, slots=True)
class CommunityOverlayAccess:
    channel_id: str
    public_key: UUID
    enabled: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CommunityOverlayEvent:
    id: int
    channel_id: str
    event_type: str
    schema_version: int
    source: str
    actor_user_id: str | None
    actor_display_name: str | None
    payload: dict
    occurred_at: datetime
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class CommunityOverlayFeed:
    cursor: int
    events: tuple[CommunityOverlayEvent, ...]


@dataclass(frozen=True, slots=True)
class CommunityOverlayThemePublished:
    revision_id: int | None
    renderer: str
    schema_version: int
    theme: dict[str, object]
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class CommunityOverlaySnapshot:
    channel_id: str
    cursor: int
    events: tuple[CommunityOverlayEvent, ...]
    themes: dict[str, CommunityOverlayThemePublished]


@dataclass(frozen=True, slots=True)
class CommunityOverlayThemeState:
    channel_id: str
    block_type: str
    renderer: str
    schema_version: int
    draft_theme: dict[str, object]
    published: CommunityOverlayThemePublished
    updated_at: datetime
    draft_version: int = 1

    @property
    def has_unpublished_changes(self) -> bool:
        return self.draft_theme != self.published.theme
