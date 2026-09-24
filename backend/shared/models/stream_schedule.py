"""Typed records for the stream schedule feature.

Two-tier model: a StreamSchedule is the "plan" level (recurring weekday or
one-off date, start time + duration) — the granularity that Phase 2 syncs to
a Twitch Schedule segment. StreamScheduleSegment rows are sub-blocks inside a
plan (offset from the plan's start) that drive internal title/game auto-apply
only; they are never synced to Twitch. See tasks/stream-schedule.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum


class ScheduleKind(StrEnum):
    RECURRING = "recurring"
    ONE_OFF = "one_off"


@dataclass(frozen=True, slots=True)
class StreamScheduleSettings:
    channel_id: str
    timezone: str = "Asia/Taipei"
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class StreamSchedule:
    id: int
    channel_id: str
    kind: ScheduleKind
    start_time: time
    duration_minutes: int
    weekday: int | None = None  # 0 = Monday; set only when kind == RECURRING
    specific_date: date | None = None  # set only when kind == ONE_OFF
    title_template: str = ""
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class StreamScheduleSegment:
    id: int
    channel_id: str  # denormalized from the parent schedule — lets callers verify
    schedule_id: int  # ownership on segment mutations without joining stream_schedules
    offset_minutes: int
    title_template: str
    game_id: str | None = None
    game_name: str | None = None
    sort_order: int = 0
