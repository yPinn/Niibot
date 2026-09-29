"""Core resolution logic for the stream schedule feature.

The heart of the feature is `resolve_active_segment`: given "now" (already
converted to the channel's local timezone) and the day's candidate schedules,
decide which schedule + segment should currently be applied, if any.

Independent one-off and recurring schedules coexist. A recurring occurrence
is suppressed only by an explicit cancellation or replacement exception.

Both the stream.online handler and the live-session poll call the same
`resolve_active_segment` function so the two triggers can never disagree.

Cross-midnight streams: a plan starting late (e.g. 23:00) can still be
"active" after local midnight. The resolver checks yesterday's calendar day
first (in case its window is still open) before today's, so a late-night
stream doesn't snap-cut to a different plan at midnight. Each day's own
one-off schedules and recurring exceptions are evaluated independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shared.errors import InvalidInputError
from shared.models.stream_schedule import (
    ScheduleKind,
    StreamSchedule,
    StreamScheduleOccurrenceException,
    StreamScheduleSegment,
    StreamScheduleSettings,
)
from shared.repositories.stream_schedule import StreamScheduleRepository

_MIN_DURATION_MINUTES = 30
_MAX_DURATION_MINUTES = 1380
_MAX_TITLE_LENGTH = 140


class StreamScheduleBoundsError(InvalidInputError):
    code = "STREAM_SCHEDULE.BOUNDS"
    user_message = "排程內容超出可用範圍，請檢查後再試"


def _validate_duration(duration_minutes: int | None) -> None:
    if duration_minutes is not None and not (
        _MIN_DURATION_MINUTES <= duration_minutes <= _MAX_DURATION_MINUTES
    ):
        raise StreamScheduleBoundsError(fields={"duration_minutes": str(duration_minutes)})


def _validate_title(title_template: str | None) -> None:
    if title_template is not None and len(title_template) > _MAX_TITLE_LENGTH:
        raise StreamScheduleBoundsError(fields={"title_template": "max_length_140"})


def _validate_offset(offset_minutes: int | None) -> None:
    if offset_minutes is not None and not 0 <= offset_minutes < _MAX_DURATION_MINUTES:
        raise StreamScheduleBoundsError(fields={"offset_minutes": str(offset_minutes)})


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
    exceptions_by_date: dict[date, dict[int, StreamScheduleOccurrenceException]],
) -> list[StreamSchedule]:
    one_offs = one_off_by_date.get(day, [])
    exceptions = exceptions_by_date.get(day, {})
    recurring = [
        schedule
        for schedule in recurring_by_weekday.get(day.weekday(), [])
        if schedule.id not in exceptions
    ]
    return sorted([*one_offs, *recurring], key=lambda schedule: schedule.start_time)


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
    exceptions_by_date: dict[date, dict[int, StreamScheduleOccurrenceException]] | None = None,
) -> ResolvedApplication | None:
    """Pure resolution — no I/O, fully unit-testable. See module docstring for the rule."""
    today = now_local.date()
    for day in (today - timedelta(days=1), today):
        candidates = _candidates_for_day(
            day=day,
            one_off_by_date=one_off_by_date,
            recurring_by_weekday=recurring_by_weekday,
            exceptions_by_date=exceptions_by_date or {},
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
        exceptions = await self._repo.list_occurrence_exceptions(
            channel_id, start_date=yesterday, end_date=today
        )
        exceptions_by_date: dict[date, dict[int, StreamScheduleOccurrenceException]] = {}
        for exception in exceptions:
            exceptions_by_date.setdefault(exception.occurrence_date, {})[
                exception.recurring_schedule_id
            ] = exception

        return resolve_active_segment(
            now_local=now_local,
            one_off_by_date=one_off_by_date,
            recurring_by_weekday=recurring_by_weekday,
            segments_by_schedule=segments_by_schedule,
            exceptions_by_date=exceptions_by_date,
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

    async def list_occurrence_exceptions(
        self, channel_id: str, *, start_date: date | None = None, end_date: date | None = None
    ) -> list[StreamScheduleOccurrenceException]:
        return await self._repo.list_occurrence_exceptions(
            channel_id, start_date=start_date, end_date=end_date
        )

    async def cancel_occurrence(
        self, channel_id: str, recurring_schedule_id: int, occurrence_date: date
    ) -> StreamScheduleOccurrenceException | None:
        return await self._repo.cancel_occurrence(
            channel_id, recurring_schedule_id, occurrence_date
        )

    async def restore_occurrence(
        self, channel_id: str, recurring_schedule_id: int, occurrence_date: date
    ) -> bool:
        return await self._repo.restore_occurrence(
            channel_id, recurring_schedule_id, occurrence_date
        )

    async def create_replacement(
        self, channel_id: str, recurring_schedule_id: int, occurrence_date: date
    ) -> tuple[StreamScheduleOccurrenceException, StreamSchedule] | None:
        return await self._repo.create_replacement(
            channel_id, recurring_schedule_id, occurrence_date
        )

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
        game_id: str | None = None,
        game_name: str | None = None,
    ) -> StreamSchedule:
        _validate_duration(duration_minutes)
        _validate_title(title_template)
        if kind is ScheduleKind.RECURRING:
            if weekday is None or specific_date is not None:
                raise ValueError("recurring schedules require weekday and no specific_date")
            return await self._repo.create_recurring(
                channel_id,
                weekday=weekday,
                start_time=start_time,
                duration_minutes=duration_minutes,
                title_template=title_template,
                game_id=game_id,
                game_name=game_name,
            )
        if specific_date is None or weekday is not None:
            raise ValueError("one-off schedules require specific_date and no weekday")
        return await self._repo.create_one_off(
            channel_id,
            specific_date=specific_date,
            start_time=start_time,
            duration_minutes=duration_minutes,
            title_template=title_template,
            game_id=game_id,
            game_name=game_name,
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
        _validate_duration(duration_minutes)
        _validate_title(title_template)
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
        _validate_offset(offset_minutes)
        _validate_title(title_template)
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
        _validate_offset(offset_minutes)
        _validate_title(title_template)
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
        """Return the next non-cancelled occurrence within seven days."""
        settings = await self._repo.get_or_create_settings(channel_id)
        now_local = now_utc.astimezone(ZoneInfo(settings.timezone))
        today = now_local.date()
        end_date = today + timedelta(days=6)
        exceptions = await self._repo.list_occurrence_exceptions(
            channel_id, start_date=today, end_date=end_date
        )
        exceptions_by_date: dict[date, dict[int, StreamScheduleOccurrenceException]] = {}
        for exception in exceptions:
            exceptions_by_date.setdefault(exception.occurrence_date, {})[
                exception.recurring_schedule_id
            ] = exception

        for offset in range(7):
            day = today + timedelta(days=offset)
            one_offs = await self._repo.list_one_off_for_date(channel_id, day)
            recurring = await self._repo.list_recurring_for_weekday(channel_id, day.weekday())
            candidates = _candidates_for_day(
                day=day,
                one_off_by_date={day: one_offs},
                recurring_by_weekday={day.weekday(): recurring},
                exceptions_by_date=exceptions_by_date,
            )
            for schedule in candidates:
                window_start = now_local.replace(
                    year=day.year,
                    month=day.month,
                    day=day.day,
                    hour=schedule.start_time.hour,
                    minute=schedule.start_time.minute,
                    second=schedule.start_time.second,
                    microsecond=0,
                )
                if (
                    offset == 0
                    and window_start + timedelta(minutes=schedule.duration_minutes) <= now_local
                ):
                    continue
                segments = await self._repo.list_segments(channel_id, schedule.id)
                return UpcomingSchedule(
                    date=day, days_from_today=offset, schedule=schedule, segments=segments
                )
        return None
