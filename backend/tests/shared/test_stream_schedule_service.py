"""Tests for shared.services.stream_schedule_service.

resolve_active_segment is the heart of the stream schedule feature: given
"now" and a day's candidate schedules, decide what (if anything) to
auto-apply. These are pure unit tests — no DB. See tasks/stream-schedule.md
for the occurrence-resolution rules these tests lock in.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from shared.errors import InvalidInputError
from shared.models.stream_schedule import (
    ScheduleKind,
    StreamSchedule,
    StreamScheduleOccurrenceException,
    StreamScheduleSegment,
    StreamScheduleSettings,
)
from shared.services.stream_schedule_service import (
    StreamScheduleService,
    resolve_active_segment,
)
from shared.stream_schedule_validation import find_schedule_conflict

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


@pytest.mark.parametrize("duration_minutes", [29, 1381])
async def test_service_rejects_unpublishable_schedule_duration(
    duration_minutes: int,
) -> None:
    repo = AsyncMock()
    service = StreamScheduleService(repo)

    with pytest.raises(InvalidInputError):
        await service.create_schedule(
            "chan1",
            kind=ScheduleKind.RECURRING,
            weekday=0,
            specific_date=None,
            start_time=time(20, 0),
            duration_minutes=duration_minutes,
        )

    repo.create_recurring.assert_not_awaited()


async def test_service_rejects_schedule_title_over_140_characters() -> None:
    repo = AsyncMock()
    service = StreamScheduleService(repo)

    with pytest.raises(InvalidInputError):
        await service.update_schedule("chan1", 1, title_template="a" * 141)

    repo.update.assert_not_awaited()


@pytest.mark.parametrize(
    ("offset_minutes", "title_template"),
    [(-1, "valid"), (1380, "valid"), (0, "a" * 141)],
)
async def test_service_rejects_unpublishable_segment_values(
    offset_minutes: int, title_template: str
) -> None:
    repo = AsyncMock()
    service = StreamScheduleService(repo)

    with pytest.raises(InvalidInputError):
        await service.add_segment(
            "chan1",
            1,
            offset_minutes=offset_minutes,
            title_template=title_template,
        )

    repo.add_segment.assert_not_awaited()


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


def test_independent_one_off_does_not_suppress_recurring_for_the_whole_day() -> None:
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

    assert result is not None
    assert result.schedule.id == recurring.id


def test_cancelled_occurrence_suppresses_only_its_recurring_schedule() -> None:
    today = date(2026, 9, 21)
    cancelled = _schedule(1, weekday=0, start_time=time(20, 0))
    other = _schedule(2, weekday=0, start_time=time(23, 0), duration_minutes=60)
    exception = StreamScheduleOccurrenceException(
        id=1,
        channel_id="chan1",
        recurring_schedule_id=cancelled.id,
        occurrence_date=today,
        kind="cancelled",
    )

    result = resolve_active_segment(
        now_local=datetime(2026, 9, 21, 20, 30, tzinfo=TZ),
        one_off_by_date={today: []},
        recurring_by_weekday={0: [cancelled, other]},
        segments_by_schedule={1: [_segment(1, 1, 0)], 2: [_segment(2, 2, 0)]},
        exceptions_by_date={today: {cancelled.id: exception}},
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


def test_overlap_detects_recurring_cross_midnight_into_next_weekday() -> None:
    monday_late = _schedule(1, weekday=0, start_time=time(23, 0), duration_minutes=180)
    tuesday_early = _schedule(2, weekday=1, start_time=time(1, 0), duration_minutes=60)

    assert find_schedule_conflict(tuesday_early, [monday_late], set()) == monday_late


def test_overlap_allows_adjacent_windows() -> None:
    first = _schedule(1, weekday=0, start_time=time(20, 0), duration_minutes=120)
    adjacent = _schedule(2, weekday=0, start_time=time(22, 0), duration_minutes=60)

    assert find_schedule_conflict(adjacent, [first], set()) is None


def test_one_off_ignores_cancelled_recurring_occurrence_for_overlap() -> None:
    recurring = _schedule(1, weekday=0, start_time=time(20, 0), duration_minutes=180)
    one_off = _schedule(
        2,
        kind=ScheduleKind.ONE_OFF,
        weekday=None,
        specific_date=_TODAY,
        start_time=time(20, 0),
        duration_minutes=180,
    )

    assert find_schedule_conflict(one_off, [recurring], {(recurring.id, _TODAY)}) is None


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


async def test_service_uses_configured_timezone_for_calendar_day() -> None:
    repo = AsyncMock()
    repo.get_or_create_settings.return_value = StreamScheduleSettings(
        channel_id="chan1", timezone="America/Los_Angeles", enabled=True
    )
    repo.list_one_off_for_date.return_value = []
    repo.list_recurring_for_weekday.return_value = []
    repo.list_segments_for_schedules.return_value = {}
    service = StreamScheduleService(repo)

    # Asia/Taipei is already Tuesday; Los Angeles is still Monday.
    await service.resolve_for_channel(
        "chan1", datetime(2026, 9, 21, 16, 30, tzinfo=ZoneInfo("UTC"))
    )

    queried_dates = [call.args[1] for call in repo.list_one_off_for_date.await_args_list]
    assert queried_dates == [date(2026, 9, 20), date(2026, 9, 21)]


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


async def test_describe_upcoming_still_queries_when_auto_apply_is_disabled() -> None:
    repo = AsyncMock()
    repo.get_or_create_settings.return_value = StreamScheduleSettings(
        channel_id="chan1", timezone="Asia/Taipei", enabled=False
    )
    service = StreamScheduleService(repo)

    result = await service.describe_upcoming("chan1", _NOW_UTC)

    assert result is None
    repo.list_one_off_for_date.assert_awaited()


async def test_describe_upcoming_orders_one_off_and_recurring_by_start_time() -> None:
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
    repo.list_recurring_for_weekday.assert_awaited_once_with("chan1", 0)
