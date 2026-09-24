"""Tests for shared.services.stream_schedule_service.

resolve_active_segment is the heart of the stream schedule feature: given
"now" and a day's candidate schedules, decide what (if anything) to
auto-apply. These are pure unit tests — no DB. See tasks/stream-schedule.md
for the day-level-override rule these tests lock in.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from shared.models.stream_schedule import (
    ScheduleKind,
    StreamSchedule,
    StreamScheduleSegment,
    StreamScheduleSettings,
)
from shared.services.stream_schedule_service import (
    StreamScheduleService,
    resolve_active_segment,
)

# 2026-09-21 is a Monday.
_TODAY = date(2026, 9, 21)
_NOW_UTC = datetime(2026, 9, 21, 3, 0, tzinfo=ZoneInfo("UTC"))  # 11:00 Asia/Taipei

TZ = ZoneInfo("Asia/Taipei")


def _schedule(
    id: int,
    *,
    kind: ScheduleKind = ScheduleKind.RECURRING,
    weekday: int | None = 0,
    specific_date: date | None = None,
    start_time: time = time(20, 0),
    duration_minutes: int = 180,
) -> StreamSchedule:
    return StreamSchedule(
        id=id,
        channel_id="chan1",
        kind=kind,
        weekday=weekday,
        specific_date=specific_date,
        start_time=start_time,
        duration_minutes=duration_minutes,
    )


def _segment(
    id: int, schedule_id: int, offset_minutes: int, *, game_name: str = ""
) -> StreamScheduleSegment:
    return StreamScheduleSegment(
        id=id,
        channel_id="chan1",
        schedule_id=schedule_id,
        offset_minutes=offset_minutes,
        title_template=f"segment-{id}",
        game_name=game_name,
    )


def test_no_candidates_returns_none() -> None:
    now = datetime(2026, 9, 21, 20, 30, tzinfo=TZ)  # Monday
    result = resolve_active_segment(
        now_local=now,
        one_off_by_date={},
        recurring_by_weekday={},
        segments_by_schedule={},
    )
    assert result is None


def test_recurring_matches_first_segment_at_start() -> None:
    schedule = _schedule(1, weekday=0, start_time=time(20, 0), duration_minutes=180)
    segments = [_segment(1, 1, 0, game_name="聊天"), _segment(2, 1, 60, game_name="Game A")]
    now = datetime(2026, 9, 21, 20, 5, tzinfo=TZ)  # Monday, 5 min after start

    result = resolve_active_segment(
        now_local=now,
        one_off_by_date={},
        recurring_by_weekday={0: [schedule]},
        segments_by_schedule={1: segments},
    )

    assert result is not None
    assert result.segment.id == 1


def test_recurring_advances_to_later_segment_mid_stream() -> None:
    schedule = _schedule(1, weekday=0, start_time=time(20, 0), duration_minutes=180)
    segments = [_segment(1, 1, 0, game_name="聊天"), _segment(2, 1, 60, game_name="Game A")]
    now = datetime(2026, 9, 21, 21, 5, tzinfo=TZ)  # 65 min after start — past the 60-min offset

    result = resolve_active_segment(
        now_local=now,
        one_off_by_date={},
        recurring_by_weekday={0: [schedule]},
        segments_by_schedule={1: segments},
    )

    assert result is not None
    assert result.segment.id == 2


def test_window_matches_but_no_segment_defined_yet_returns_none() -> None:
    schedule = _schedule(1, weekday=0, start_time=time(20, 0), duration_minutes=180)
    segments = [_segment(1, 1, 30, game_name="Game A")]  # first segment starts 30 min in
    now = datetime(2026, 9, 21, 20, 10, tzinfo=TZ)  # only 10 min in — before any segment

    result = resolve_active_segment(
        now_local=now,
        one_off_by_date={},
        recurring_by_weekday={0: [schedule]},
        segments_by_schedule={1: segments},
    )

    assert result is None


def test_one_off_present_suppresses_recurring_even_outside_its_own_window() -> None:
    """Day-level override: today's one-off exists, so recurring is fully suppressed
    for today — even though `now` is outside the one-off's window and would have
    matched the recurring plan's window. Prevents mid-stream snap-back."""
    today = date(2026, 9, 21)  # Monday
    recurring = _schedule(1, weekday=0, start_time=time(20, 0), duration_minutes=180)
    one_off = _schedule(
        2,
        kind=ScheduleKind.ONE_OFF,
        weekday=None,
        specific_date=today,
        start_time=time(19, 0),
        duration_minutes=60,
    )
    # now is inside recurring's 20:00-23:00 window, but the one-off (19:00-20:00) has ended
    now = datetime(2026, 9, 21, 21, 0, tzinfo=TZ)

    result = resolve_active_segment(
        now_local=now,
        one_off_by_date={today: [one_off]},
        recurring_by_weekday={0: [recurring]},
        segments_by_schedule={1: [_segment(1, 1, 0)], 2: [_segment(2, 2, 0)]},
    )

    assert result is None


def test_falls_back_to_recurring_when_no_one_off_today() -> None:
    today = date(2026, 9, 21)
    recurring = _schedule(1, weekday=0, start_time=time(20, 0), duration_minutes=180)
    now = datetime(2026, 9, 21, 20, 30, tzinfo=TZ)

    result = resolve_active_segment(
        now_local=now,
        one_off_by_date={today: []},
        recurring_by_weekday={0: [recurring]},
        segments_by_schedule={1: [_segment(1, 1, 0)]},
    )

    assert result is not None
    assert result.schedule.id == 1


def test_cross_midnight_stream_still_resolves_to_yesterdays_plan() -> None:
    """A plan starting 23:00 for duration 240 (until 03:00) must still resolve
    at 01:00 the next calendar day — not snap to whatever "today" would be."""
    schedule = _schedule(
        1,
        weekday=6,
        start_time=time(23, 0),
        duration_minutes=240,  # 6 = Sunday
    )
    now = datetime(2026, 9, 21, 1, 0, tzinfo=TZ)  # Monday 01:00 — inside yesterday's window

    result = resolve_active_segment(
        now_local=now,
        one_off_by_date={},
        recurring_by_weekday={6: [schedule]},
        segments_by_schedule={1: [_segment(1, 1, 0, game_name="夜間節目")]},
    )

    assert result is not None
    assert result.schedule.id == 1


async def test_service_short_circuits_when_disabled() -> None:
    repo = AsyncMock()
    repo.get_or_create_settings.return_value = StreamScheduleSettings(
        channel_id="chan1", timezone="Asia/Taipei", enabled=False
    )
    service = StreamScheduleService(repo)

    result = await service.resolve_for_channel(
        "chan1", datetime(2026, 9, 21, 20, 30, tzinfo=ZoneInfo("UTC"))
    )

    assert result is None
    repo.list_one_off_for_date.assert_not_called()


async def test_service_resolves_through_repository() -> None:
    repo = AsyncMock()
    repo.get_or_create_settings.return_value = StreamScheduleSettings(
        channel_id="chan1", timezone="Asia/Taipei", enabled=True
    )
    schedule = _schedule(1, weekday=0, start_time=time(20, 0), duration_minutes=180)
    repo.list_one_off_for_date.return_value = []
    repo.list_recurring_for_weekday.side_effect = lambda channel_id, weekday: (
        [schedule] if weekday == 0 else []
    )
    repo.list_segments_for_schedules.return_value = {1: [_segment(1, 1, 0, game_name="Game A")]}
    service = StreamScheduleService(repo)

    # 2026-09-21 20:30 Asia/Taipei == 12:30 UTC
    now_utc = datetime(2026, 9, 21, 12, 30, tzinfo=ZoneInfo("UTC"))
    result = await service.resolve_for_channel("chan1", now_utc)

    assert result is not None
    assert result.segment.game_name == "Game A"


def _repo_with_schedule_on(target_day: date, schedule: StreamSchedule) -> AsyncMock:
    """A repo mock where only `target_day` (by date or matching weekday) has a schedule."""
    repo = AsyncMock()
    repo.get_or_create_settings.return_value = StreamScheduleSettings(
        channel_id="chan1", timezone="Asia/Taipei", enabled=True
    )
    repo.list_one_off_for_date.return_value = []

    async def _recurring(channel_id: str, weekday: int) -> list[StreamSchedule]:
        return [schedule] if weekday == target_day.weekday() else []

    repo.list_recurring_for_weekday.side_effect = _recurring
    repo.list_segments.return_value = []
    return repo


async def test_describe_upcoming_finds_todays_schedule() -> None:
    schedule = _schedule(1, weekday=_TODAY.weekday(), start_time=time(20, 0))
    repo = _repo_with_schedule_on(_TODAY, schedule)
    service = StreamScheduleService(repo)

    result = await service.describe_upcoming("chan1", _NOW_UTC)

    assert result is not None
    assert result.date == _TODAY
    assert result.schedule.id == 1


async def test_describe_upcoming_looks_ahead_when_nothing_today() -> None:
    tomorrow = _TODAY + timedelta(days=1)
    schedule = _schedule(2, weekday=tomorrow.weekday(), start_time=time(20, 0))
    repo = _repo_with_schedule_on(tomorrow, schedule)
    service = StreamScheduleService(repo)

    result = await service.describe_upcoming("chan1", _NOW_UTC)

    assert result is not None
    assert result.date == tomorrow
    assert result.schedule.id == 2


async def test_describe_upcoming_returns_none_within_a_week_of_silence() -> None:
    repo = AsyncMock()
    repo.get_or_create_settings.return_value = StreamScheduleSettings(
        channel_id="chan1", timezone="Asia/Taipei", enabled=True
    )
    repo.list_one_off_for_date.return_value = []
    repo.list_recurring_for_weekday.return_value = []
    service = StreamScheduleService(repo)

    result = await service.describe_upcoming("chan1", _NOW_UTC)

    assert result is None
    assert repo.list_recurring_for_weekday.await_count == 7


async def test_describe_upcoming_short_circuits_when_disabled() -> None:
    repo = AsyncMock()
    repo.get_or_create_settings.return_value = StreamScheduleSettings(
        channel_id="chan1", timezone="Asia/Taipei", enabled=False
    )
    service = StreamScheduleService(repo)

    result = await service.describe_upcoming("chan1", _NOW_UTC)

    assert result is None
    repo.list_one_off_for_date.assert_not_called()


async def test_describe_upcoming_prefers_one_off_over_recurring_on_the_matched_day() -> None:
    recurring = _schedule(1, weekday=_TODAY.weekday(), start_time=time(20, 0))
    one_off = _schedule(
        2, kind=ScheduleKind.ONE_OFF, weekday=None, specific_date=_TODAY, start_time=time(19, 0)
    )
    repo = AsyncMock()
    repo.get_or_create_settings.return_value = StreamScheduleSettings(
        channel_id="chan1", timezone="Asia/Taipei", enabled=True
    )

    async def _one_off(channel_id: str, day: date) -> list[StreamSchedule]:
        return [one_off] if day == _TODAY else []

    repo.list_one_off_for_date.side_effect = _one_off
    repo.list_recurring_for_weekday.return_value = [recurring]
    repo.list_segments.return_value = []
    service = StreamScheduleService(repo)

    result = await service.describe_upcoming("chan1", _NOW_UTC)

    assert result is not None
    assert result.schedule.id == 2
    repo.list_recurring_for_weekday.assert_not_called()
