from __future__ import annotations

from datetime import date, time, timedelta

from shared.models.stream_schedule import ScheduleKind, StreamSchedule

_MINUTES_PER_DAY = 1440
_MINUTES_PER_WEEK = 7 * _MINUTES_PER_DAY


def _time_minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _windows_overlap(start_a: int, duration_a: int, start_b: int, duration_b: int) -> bool:
    return start_a < start_b + duration_b and start_b < start_a + duration_a


def find_schedule_conflict(
    candidate: StreamSchedule,
    existing: list[StreamSchedule],
    suppressed_occurrences: set[tuple[int, date]],
) -> StreamSchedule | None:
    """Return the first enabled schedule whose occurrence overlaps the candidate."""
    for other in existing:
        if not other.enabled or (candidate.id > 0 and other.id == candidate.id):
            continue

        if candidate.kind is ScheduleKind.RECURRING and other.kind is ScheduleKind.RECURRING:
            assert candidate.weekday is not None and other.weekday is not None
            candidate_start = candidate.weekday * _MINUTES_PER_DAY + _time_minutes(
                candidate.start_time
            )
            other_start = other.weekday * _MINUTES_PER_DAY + _time_minutes(other.start_time)
            if any(
                _windows_overlap(
                    candidate_start,
                    candidate.duration_minutes,
                    other_start + shift,
                    other.duration_minutes,
                )
                for shift in (-_MINUTES_PER_WEEK, 0, _MINUTES_PER_WEEK)
            ):
                return other
            continue

        if candidate.kind is ScheduleKind.ONE_OFF and other.kind is ScheduleKind.ONE_OFF:
            assert candidate.specific_date is not None and other.specific_date is not None
            candidate_start = (
                candidate.specific_date.toordinal() * _MINUTES_PER_DAY
                + _time_minutes(candidate.start_time)
            )
            other_start = other.specific_date.toordinal() * _MINUTES_PER_DAY + _time_minutes(
                other.start_time
            )
            if _windows_overlap(
                candidate_start,
                candidate.duration_minutes,
                other_start,
                other.duration_minutes,
            ):
                return other
            continue

        recurring = candidate if candidate.kind is ScheduleKind.RECURRING else other
        one_off = candidate if candidate.kind is ScheduleKind.ONE_OFF else other
        assert recurring.weekday is not None and one_off.specific_date is not None
        one_off_start = one_off.specific_date.toordinal() * _MINUTES_PER_DAY + _time_minutes(
            one_off.start_time
        )
        week_start = one_off.specific_date - timedelta(days=one_off.specific_date.weekday())
        for week_shift in (-7, 0, 7):
            occurrence_date = week_start + timedelta(days=recurring.weekday + week_shift)
            if (recurring.id, occurrence_date) in suppressed_occurrences:
                continue
            recurring_start = occurrence_date.toordinal() * _MINUTES_PER_DAY + _time_minutes(
                recurring.start_time
            )
            if _windows_overlap(
                one_off_start,
                one_off.duration_minutes,
                recurring_start,
                recurring.duration_minutes,
            ):
                return other
    return None
