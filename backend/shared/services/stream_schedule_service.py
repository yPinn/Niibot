"""Core resolution logic for the stream schedule feature.

The heart of the feature is `resolve_active_segment`: given "now" (already
converted to the channel's local timezone) and the day's candidate schedules,
decide which schedule + segment should currently be applied, if any.

Conflict rule (day-level override, not interval-level — see
tasks/stream-schedule.md for the full rationale): for a given calendar day,
if any enabled one-off schedule exists on that date, recurring schedules are
fully suppressed for that day, regardless of whether "now" falls inside the
one-off's own window. Outside all of a day's candidate windows, the resolver
returns None (no auto-apply) rather than falling back to a different plan —
`duration_minutes` is an estimate, not a hard boundary, and a stream that
runs long must never silently snap back to a different plan mid-broadcast.

Both the stream.online handler and the live-session poll call the same
`resolve_active_segment` function so the two triggers can never disagree.

Cross-midnight streams: a plan starting late (e.g. 23:00) can still be
"active" after local midnight. The resolver checks yesterday's calendar day
first (in case its window is still open) before today's, so a late-night
stream doesn't snap-cut to a different plan at midnight. Each day's own
one-off-vs-recurring override is still evaluated independently per day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shared.models.stream_schedule import (
    ScheduleKind,
    StreamSchedule,
    StreamScheduleSegment,
    StreamScheduleSettings,
)
from shared.repositories.stream_schedule import StreamScheduleRepository


@dataclass(frozen=True, slots=True)
class ResolvedApplication:
    schedule: StreamSchedule
    segment: StreamScheduleSegment


@dataclass(frozen=True, slots=True)
class UpcomingSchedule:
    """A day's plan for !schedule — day-level only, unlike ResolvedApplication
    which additionally resolves the active segment for "right now"."""

    date: date
    days_from_today: int  # 0 = today, 1 = tomorrow, ... — display layer's to phrase, not tz math
    schedule: StreamSchedule
    segments: list[StreamScheduleSegment]


def _candidates_for_day(
    *,
    day: date,
    one_off_by_date: dict[date, list[StreamSchedule]],
    recurring_by_weekday: dict[int, list[StreamSchedule]],
) -> list[StreamSchedule]:
    """Day-level override: a day's one-offs, if any, fully replace its recurring plans."""
    one_offs = one_off_by_date.get(day, [])
    if one_offs:
        return one_offs
    return recurring_by_weekday.get(day.weekday(), [])


def _active_segment_at(
    segments: list[StreamScheduleSegment], elapsed_minutes: float
) -> StreamScheduleSegment | None:
    """Latest segment whose offset has been reached. `segments` must be offset-sorted."""
    active: StreamScheduleSegment | None = None
    for segment in segments:
        if segment.offset_minutes <= elapsed_minutes:
            active = segment
        else:
            break
    return active


def resolve_active_segment(
    *,
    now_local: datetime,
    one_off_by_date: dict[date, list[StreamSchedule]],
    recurring_by_weekday: dict[int, list[StreamSchedule]],
    segments_by_schedule: dict[int, list[StreamScheduleSegment]],
) -> ResolvedApplication | None:
    """Pure resolution — no I/O, fully unit-testable. See module docstring for the rule."""
    today = now_local.date()
    for day in (today - timedelta(days=1), today):
        candidates = _candidates_for_day(
            day=day, one_off_by_date=one_off_by_date, recurring_by_weekday=recurring_by_weekday
        )
        for schedule in candidates:
            anchor_date = schedule.specific_date or day
            window_start = now_local.replace(
                year=anchor_date.year,
                month=anchor_date.month,
                day=anchor_date.day,
                hour=schedule.start_time.hour,
                minute=schedule.start_time.minute,
                second=schedule.start_time.second,
                microsecond=0,
            )
            window_end = window_start + timedelta(minutes=schedule.duration_minutes)
            if not (window_start <= now_local < window_end):
                continue

            segments = segments_by_schedule.get(schedule.id, [])
            elapsed_minutes = (now_local - window_start).total_seconds() / 60
            active_segment = _active_segment_at(segments, elapsed_minutes)
            if active_segment is None:
                # Day is claimed by this schedule, but no segment starts yet — no-op,
                # do NOT fall through to another day/schedule.
                return None
            return ResolvedApplication(schedule=schedule, segment=active_segment)
    return None


class StreamScheduleService:
    def __init__(self, repo: StreamScheduleRepository) -> None:
        self._repo = repo

    async def resolve_for_channel(
        self, channel_id: str, now_utc: datetime
    ) -> ResolvedApplication | None:
        """Entry point for both the stream.online handler and the live-session poll."""
        settings = await self._repo.get_or_create_settings(channel_id)
        if not settings.enabled:
            return None

        now_local = now_utc.astimezone(ZoneInfo(settings.timezone))
        today = now_local.date()
        yesterday = today - timedelta(days=1)

        one_off_by_date: dict[date, list[StreamSchedule]] = {}
        recurring_by_weekday: dict[int, list[StreamSchedule]] = {}
        for day in (yesterday, today):
            one_off_by_date[day] = await self._repo.list_one_off_for_date(channel_id, day)
            recurring_by_weekday[day.weekday()] = await self._repo.list_recurring_for_weekday(
                channel_id, day.weekday()
            )

        candidate_ids = [
            s.id
            for schedules in (*one_off_by_date.values(), *recurring_by_weekday.values())
            for s in schedules
        ]
        segments_by_schedule = await self._repo.list_segments_for_schedules(candidate_ids)

        return resolve_active_segment(
            now_local=now_local,
            one_off_by_date=one_off_by_date,
            recurring_by_weekday=recurring_by_weekday,
            segments_by_schedule=segments_by_schedule,
        )

    # ------------------------------------------------------------------
    # CRUD passthroughs for the dashboard router
    # ------------------------------------------------------------------

    async def get_settings(self, channel_id: str) -> StreamScheduleSettings:
        return await self._repo.get_or_create_settings(channel_id)

    async def update_settings(
        self, channel_id: str, *, timezone: str | None = None, enabled: bool | None = None
    ) -> StreamScheduleSettings:
        if timezone is not None:
            try:
                ZoneInfo(timezone)
            except (ZoneInfoNotFoundError, ValueError) as e:
                raise ValueError(f"invalid timezone: {timezone}") from e
        return await self._repo.update_settings(channel_id, timezone=timezone, enabled=enabled)

    async def list_schedules(self, channel_id: str) -> list[StreamSchedule]:
        return await self._repo.list_all(channel_id)

    async def get_schedule(self, channel_id: str, schedule_id: int) -> StreamSchedule | None:
        return await self._repo.get(channel_id, schedule_id)

    async def create_schedule(
        self,
        channel_id: str,
        *,
        kind: ScheduleKind,
        weekday: int | None,
        specific_date: date | None,
        start_time: time,
        duration_minutes: int,
        title_template: str = "",
    ) -> StreamSchedule:
        if kind is ScheduleKind.RECURRING:
            if weekday is None or specific_date is not None:
                raise ValueError("recurring schedules require weekday and no specific_date")
            return await self._repo.create_recurring(
                channel_id,
                weekday=weekday,
                start_time=start_time,
                duration_minutes=duration_minutes,
                title_template=title_template,
            )
        if specific_date is None or weekday is not None:
            raise ValueError("one-off schedules require specific_date and no weekday")
        return await self._repo.create_one_off(
            channel_id,
            specific_date=specific_date,
            start_time=start_time,
            duration_minutes=duration_minutes,
            title_template=title_template,
        )

    async def update_schedule(
        self,
        channel_id: str,
        schedule_id: int,
        *,
        start_time: time | None = None,
        duration_minutes: int | None = None,
        title_template: str | None = None,
        enabled: bool | None = None,
    ) -> StreamSchedule | None:
        return await self._repo.update(
            channel_id,
            schedule_id,
            start_time=start_time,
            duration_minutes=duration_minutes,
            title_template=title_template,
            enabled=enabled,
        )

    async def delete_schedule(self, channel_id: str, schedule_id: int) -> bool:
        return await self._repo.delete(channel_id, schedule_id)

    async def list_segments(self, channel_id: str, schedule_id: int) -> list[StreamScheduleSegment]:
        return await self._repo.list_segments(channel_id, schedule_id)

    async def add_segment(
        self,
        channel_id: str,
        schedule_id: int,
        *,
        offset_minutes: int,
        title_template: str,
        game_id: str | None = None,
        game_name: str | None = None,
        sort_order: int = 0,
    ) -> StreamScheduleSegment | None:
        return await self._repo.add_segment(
            channel_id,
            schedule_id,
            offset_minutes=offset_minutes,
            title_template=title_template,
            game_id=game_id,
            game_name=game_name,
            sort_order=sort_order,
        )

    async def update_segment(
        self,
        channel_id: str,
        segment_id: int,
        *,
        offset_minutes: int | None = None,
        title_template: str | None = None,
        game_id: str | None = None,
        game_name: str | None = None,
        sort_order: int | None = None,
        clear_game: bool = False,
    ) -> StreamScheduleSegment | None:
        return await self._repo.update_segment(
            channel_id,
            segment_id,
            offset_minutes=offset_minutes,
            title_template=title_template,
            game_id=game_id,
            game_name=game_name,
            sort_order=sort_order,
            clear_game=clear_game,
        )

    async def delete_segment(self, channel_id: str, segment_id: int) -> bool:
        return await self._repo.delete_segment(channel_id, segment_id)

    # ------------------------------------------------------------------
    # Query — !schedule / !下次開台
    # ------------------------------------------------------------------

    async def describe_upcoming(
        self, channel_id: str, now_utc: datetime
    ) -> UpcomingSchedule | None:
        """Today's plan, or the soonest day within a week that has one.

        Day-level only (same one-off-over-recurring override as the resolver)
        — unlike resolve_active_segment, this does not check whether "now"
        falls inside the window, so it still answers today even if the
        stream already ended, and still finds a same-weekday recurring plan
        next week if nothing is scheduled sooner.
        """
        settings = await self._repo.get_or_create_settings(channel_id)
        if not settings.enabled:
            return None

        now_local = now_utc.astimezone(ZoneInfo(settings.timezone))
        today = now_local.date()
        for offset in range(7):
            day = today + timedelta(days=offset)
            candidates = await self._repo.list_one_off_for_date(channel_id, day)
            if not candidates:
                candidates = await self._repo.list_recurring_for_weekday(channel_id, day.weekday())
            if not candidates:
                continue
            schedule = candidates[0]
            segments = await self._repo.list_segments(channel_id, schedule.id)
            return UpcomingSchedule(
                date=day, days_from_today=offset, schedule=schedule, segments=segments
            )
        return None
