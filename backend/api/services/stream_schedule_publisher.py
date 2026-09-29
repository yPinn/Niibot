"""One-way Niibot -> Twitch public schedule publication."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from services.twitch_api import TwitchAPIClient, TwitchScheduleAPIError
from shared.models.stream_schedule import (
    ScheduleKind,
    StreamSchedule,
    StreamScheduleSegment,
    TwitchScheduleOccurrenceState,
    TwitchSchedulePublishState,
)
from shared.repositories.channel import ChannelRepository
from shared.repositories.stream_schedule import StreamScheduleRepository
from shared.repositories.stream_schedule_publish import StreamSchedulePublishRepository
from shared.twitch_scopes import capability_available

if TYPE_CHECKING:
    from shared.models.channel import Token

LOGGER: logging.Logger = logging.getLogger(__name__)


class PublishAction(StrEnum):
    NONE = "none"
    CREATE = "create"
    UPDATE = "update"
    RECREATE = "recreate"
    DELETE = "delete"


@dataclass(frozen=True, slots=True)
class TwitchSchedulePayload:
    start_time: str
    timezone: str
    duration_minutes: int
    is_recurring: bool
    title: str | None
    category_id: str | None
    identity_key: str
    fingerprint: str


def _rfc3339(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_publish_payload(
    schedule: StreamSchedule,
    opening: StreamScheduleSegment,
    *,
    timezone: str,
    now_utc: datetime,
) -> TwitchSchedulePayload | None:
    zone = ZoneInfo(timezone)
    now_local = now_utc.astimezone(zone)
    if schedule.kind is ScheduleKind.RECURRING:
        assert schedule.weekday is not None
        days = (schedule.weekday - now_local.weekday()) % 7
        local_start = datetime.combine(
            now_local.date() + timedelta(days=days), schedule.start_time, tzinfo=zone
        )
        if local_start <= now_local:
            local_start += timedelta(days=7)
        identity_key = (
            f"recurring:{schedule.weekday}:{schedule.start_time.strftime('%H:%M')}:{timezone}"
        )
        is_recurring = True
    else:
        assert schedule.specific_date is not None
        local_start = datetime.combine(schedule.specific_date, schedule.start_time, tzinfo=zone)
        if local_start + timedelta(minutes=schedule.duration_minutes) <= now_local:
            return None
        identity_key = f"one_off:{local_start.isoformat()}"
        is_recurring = False

    start_time = _rfc3339(local_start)
    canonical = {
        "start_time": start_time,
        "timezone": timezone,
        "duration": schedule.duration_minutes,
        "is_recurring": is_recurring,
        "title": opening.title_template or None,
        "category_id": opening.game_id or None,
        "identity_key": identity_key,
    }
    fingerprint = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return TwitchSchedulePayload(
        start_time=start_time,
        timezone=timezone,
        duration_minutes=schedule.duration_minutes,
        is_recurring=is_recurring,
        title=opening.title_template or None,
        category_id=opening.game_id or None,
        identity_key=identity_key,
        fingerprint=fingerprint,
    )


def decide_publish_action(
    *,
    enabled: bool,
    payload: TwitchSchedulePayload | None,
    state: TwitchSchedulePublishState | None,
) -> PublishAction:
    if not enabled or payload is None:
        return (
            PublishAction.DELETE
            if state is not None and state.twitch_segment_id is not None
            else PublishAction.NONE
        )
    if state is None or state.twitch_segment_id is None:
        return PublishAction.CREATE
    if (
        payload.is_recurring
        and state.identity_key is not None
        and state.identity_key != payload.identity_key
    ):
        return PublishAction.RECREATE
    if state.payload_fingerprint != payload.fingerprint or state.status != "synced":
        return PublishAction.UPDATE
    return PublishAction.NONE


class StreamSchedulePublisherError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(f"Stream schedule publication failed ({code})")
        self.code = code
        self.retryable = retryable


class StreamSchedulePublisher:
    def __init__(
        self,
        schedule_repo: StreamScheduleRepository,
        publish_repo: StreamSchedulePublishRepository,
        channel_repo: ChannelRepository,
        twitch_api: TwitchAPIClient,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._schedules = schedule_repo
        self._publish = publish_repo
        self._channels = channel_repo
        self._twitch = twitch_api
        self._now = now or (lambda: datetime.now(UTC))

    async def sync_channel(self, channel_id: str) -> bool:
        """Publish one tenant and report whether occurrence work needs a later recheck."""
        settings = await self._schedules.get_or_create_settings(channel_id)
        schedules = await self._schedules.list_all(channel_id)
        schedule_by_id = {schedule.id: schedule for schedule in schedules}
        segments_by_schedule = await self._schedules.list_segments_for_schedules(
            list(schedule_by_id)
        )
        states = await self._publish.list_states(channel_id)
        state_by_schedule = {
            state.schedule_id: state for state in states if state.schedule_id is not None
        }
        token = await self._channels.get_token(channel_id, "broadcaster")

        if token is None or not capability_available(
            "stream_schedule", set((token.scopes or "").split())
        ):
            for schedule in schedules:
                if schedule.enabled:
                    await self._publish.mark_state_error(
                        channel_id,
                        schedule_id=schedule.id,
                        schedule_kind=schedule.kind,
                        error_code="missing_scope",
                        blocked=True,
                    )
            return False

        for state in states:
            if state.schedule_id is None or state.schedule_id not in schedule_by_id:
                await self._delete_orphan(channel_id, token, state)

        now_utc = self._now()
        for schedule in schedules:
            opening = next(
                (
                    segment
                    for segment in segments_by_schedule.get(schedule.id, [])
                    if segment.offset_minutes == 0
                ),
                None,
            )
            if opening is None:
                await self._publish.mark_state_error(
                    channel_id,
                    schedule_id=schedule.id,
                    schedule_kind=schedule.kind,
                    error_code="invalid_local_state",
                    blocked=True,
                )
                continue
            payload = build_publish_payload(
                schedule,
                opening,
                timezone=settings.timezone,
                now_utc=now_utc,
            )
            await self._sync_schedule(
                channel_id,
                token,
                schedule,
                payload,
                state_by_schedule.get(schedule.id),
            )

        refreshed_states = await self._publish.list_states(channel_id)
        state_by_schedule = {
            state.schedule_id: state for state in refreshed_states if state.schedule_id is not None
        }
        return await self._sync_occurrences(
            channel_id,
            token,
            settings.timezone,
            schedule_by_id,
            state_by_schedule,
            now_utc,
        )

    async def _delete_orphan(
        self,
        channel_id: str,
        token: Token,
        state: TwitchSchedulePublishState,
    ) -> None:
        try:
            if state.twitch_segment_id:
                await self._twitch.delete_channel_stream_schedule_segment(
                    channel_id, state.twitch_segment_id, token.token
                )
        except TwitchScheduleAPIError as error:
            if error.code != "segment_not_found":
                if error.retryable:
                    raise StreamSchedulePublisherError(error.code, retryable=True) from error
                LOGGER.warning(
                    "Unable to delete orphan Twitch schedule state %s (%s)",
                    state.id,
                    error.code,
                )
                await self._publish.mark_existing_state_error(
                    channel_id,
                    state.id,
                    error_code=error.code,
                    blocked=True,
                )
                return
        await self._publish.delete_state(channel_id, state.id)

    async def _sync_schedule(
        self,
        channel_id: str,
        token: Token,
        schedule: StreamSchedule,
        payload: TwitchSchedulePayload | None,
        state: TwitchSchedulePublishState | None,
    ) -> None:
        action = decide_publish_action(
            enabled=schedule.enabled,
            payload=payload,
            state=state,
        )
        if action is PublishAction.NONE:
            return
        try:
            if action is PublishAction.DELETE:
                assert state is not None
                if state.twitch_segment_id:
                    await self._twitch.delete_channel_stream_schedule_segment(
                        channel_id, state.twitch_segment_id, token.token
                    )
                await self._publish.delete_state(channel_id, state.id)
                return

            assert payload is not None
            if action is PublishAction.RECREATE:
                assert state is not None and state.twitch_segment_id is not None
                try:
                    await self._twitch.delete_channel_stream_schedule_segment(
                        channel_id, state.twitch_segment_id, token.token
                    )
                except TwitchScheduleAPIError as error:
                    if error.code != "segment_not_found":
                        raise
                remote = await self._create_or_recover(channel_id, token, payload)
            elif action is PublishAction.CREATE:
                remote = await self._create_or_recover(channel_id, token, payload)
            else:
                assert state is not None and state.twitch_segment_id is not None
                current = await self._find_remote(channel_id, token, payload)
                if current is None:
                    remote = await self._create_or_recover(channel_id, token, payload)
                else:
                    remote = await self._twitch.update_channel_stream_schedule_segment(
                        channel_id,
                        str(current["id"]),
                        token.token,
                        start_time=None if payload.is_recurring else payload.start_time,
                        timezone=payload.timezone,
                        duration_minutes=payload.duration_minutes,
                        title=payload.title or "",
                        category_id=payload.category_id or "",
                    )
            remote_id = str(remote.get("id") or (state.twitch_segment_id if state else ""))
            if not remote_id:
                raise StreamSchedulePublisherError("invalid_response", retryable=True)
            await self._publish.mark_state_synced(
                channel_id,
                schedule_id=schedule.id,
                schedule_kind=schedule.kind,
                twitch_segment_id=remote_id,
                identity_key=payload.identity_key,
                payload_fingerprint=payload.fingerprint,
            )
        except TwitchScheduleAPIError as error:
            blocked = error.code in {
                "missing_scope",
                "unauthorized",
                "non_recurring_unsupported",
                "invalid_request",
            }
            await self._publish.mark_state_error(
                channel_id,
                schedule_id=schedule.id,
                schedule_kind=schedule.kind,
                error_code=error.code,
                blocked=blocked,
            )
            if error.retryable:
                raise StreamSchedulePublisherError(error.code, retryable=True) from error

    async def _create_or_recover(
        self,
        channel_id: str,
        token: Token,
        payload: TwitchSchedulePayload,
    ) -> dict:
        existing = await self._find_remote(channel_id, token, payload, exact_metadata=True)
        if existing is not None:
            return existing
        return await self._twitch.create_channel_stream_schedule_segment(
            channel_id,
            token.token,
            start_time=payload.start_time,
            timezone=payload.timezone,
            duration_minutes=payload.duration_minutes,
            is_recurring=payload.is_recurring,
            title=payload.title,
            category_id=payload.category_id,
        )

    async def _find_remote(
        self,
        channel_id: str,
        token: Token,
        payload: TwitchSchedulePayload,
        *,
        exact_metadata: bool = False,
    ) -> dict | None:
        remote_segments = await self._twitch.get_channel_stream_schedule(
            channel_id, token.token, start_time=payload.start_time
        )
        recovered = next(
            (
                segment
                for segment in remote_segments
                if segment.get("start_time") == payload.start_time
                and bool(segment.get("is_recurring")) is payload.is_recurring
                and (not exact_metadata or self._remote_metadata_matches(segment, payload))
            ),
            None,
        )
        return recovered

    @staticmethod
    def _remote_metadata_matches(segment: dict, payload: TwitchSchedulePayload) -> bool:
        category = segment.get("category") or {}
        if (segment.get("title") or None) != payload.title:
            return False
        if (category.get("id") or None) != payload.category_id:
            return False
        try:
            start = datetime.fromisoformat(str(segment["start_time"]).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(segment["end_time"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            return False
        return int((end - start).total_seconds() // 60) == payload.duration_minutes

    async def _sync_occurrences(
        self,
        channel_id: str,
        token: Token,
        timezone: str,
        schedule_by_id: dict[int, StreamSchedule],
        state_by_schedule: dict[int, TwitchSchedulePublishState],
        now_utc: datetime,
    ) -> bool:
        exceptions = await self._schedules.list_occurrence_exceptions(channel_id)
        exception_keys = {(item.recurring_schedule_id, item.occurrence_date) for item in exceptions}
        existing = await self._publish.list_occurrence_states(channel_id)
        desired: dict[tuple[int, date], TwitchScheduleOccurrenceState] = {}
        needs_recheck = False
        for item in exceptions:
            state = await self._publish.upsert_occurrence_desired(
                channel_id,
                recurring_schedule_id=item.recurring_schedule_id,
                occurrence_date=item.occurrence_date,
                desired_state="cancelled",
            )
            desired[(item.recurring_schedule_id, item.occurrence_date)] = state
        for state in existing:
            key = (state.recurring_schedule_id, state.occurrence_date)
            if key in exception_keys:
                continue
            desired[key] = await self._publish.upsert_occurrence_desired(
                channel_id,
                recurring_schedule_id=state.recurring_schedule_id,
                occurrence_date=state.occurrence_date,
                desired_state="active",
            )

        for state in desired.values():
            schedule = schedule_by_id.get(state.recurring_schedule_id)
            series_state = state_by_schedule.get(state.recurring_schedule_id)
            if schedule is None or schedule.kind is not ScheduleKind.RECURRING:
                await self._publish.delete_occurrence_state(channel_id, state.id)
                continue
            if series_state is None or not series_state.twitch_segment_id:
                await self._publish.mark_occurrence_status(channel_id, state.id, status="deferred")
                needs_recheck = True
                continue
            next_date = self._next_occurrence_date(schedule, timezone, now_utc)
            if state.occurrence_date > next_date:
                await self._publish.mark_occurrence_status(channel_id, state.id, status="deferred")
                needs_recheck = True
                continue
            if state.occurrence_date < next_date:
                await self._publish.delete_occurrence_state(channel_id, state.id)
                continue

            zone = ZoneInfo(timezone)
            local_start = datetime.combine(state.occurrence_date, schedule.start_time, tzinfo=zone)
            start_time = _rfc3339(local_start)
            remote = await self._twitch.get_channel_stream_schedule(
                channel_id, token.token, start_time=start_time
            )
            occurrence = next(
                (
                    item
                    for item in remote
                    if item.get("start_time") == start_time and item.get("is_recurring") is True
                ),
                None,
            )
            if occurrence is None:
                await self._publish.mark_occurrence_status(channel_id, state.id, status="deferred")
                needs_recheck = True
                continue
            try:
                updated = await self._twitch.update_channel_stream_schedule_segment(
                    channel_id,
                    str(occurrence["id"]),
                    token.token,
                    is_canceled=state.desired_state == "cancelled",
                )
            except TwitchScheduleAPIError as error:
                await self._publish.mark_occurrence_status(
                    channel_id,
                    state.id,
                    status="error" if error.retryable else "blocked",
                    error_code=error.code,
                )
                if error.retryable:
                    raise StreamSchedulePublisherError(error.code, retryable=True) from error
                continue
            if state.desired_state == "active":
                await self._publish.delete_occurrence_state(channel_id, state.id)
            else:
                await self._publish.mark_occurrence_status(
                    channel_id,
                    state.id,
                    status="synced",
                    twitch_segment_id=str(updated.get("id") or occurrence["id"]),
                )
        return needs_recheck

    @staticmethod
    def _next_occurrence_date(schedule: StreamSchedule, timezone: str, now_utc: datetime) -> date:
        assert schedule.weekday is not None
        now_local = now_utc.astimezone(ZoneInfo(timezone))
        days = (schedule.weekday - now_local.weekday()) % 7
        occurrence_date = now_local.date() + timedelta(days=days)
        local_start = datetime.combine(
            occurrence_date, schedule.start_time, tzinfo=ZoneInfo(timezone)
        )
        if local_start <= now_local:
            occurrence_date += timedelta(days=7)
        return occurrence_date
