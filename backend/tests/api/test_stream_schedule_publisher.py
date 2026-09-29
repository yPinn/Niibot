from __future__ import annotations

from datetime import UTC, date, datetime, time
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.stream_schedule_publisher import (
    PublishAction,
    StreamSchedulePublisher,
    StreamSchedulePublisherError,
    TwitchSchedulePublishState,
    build_publish_payload,
    decide_publish_action,
)
from services.twitch_api import TwitchScheduleAPIError
from shared.models.channel import Token
from shared.models.stream_schedule import (
    OccurrenceExceptionKind,
    ScheduleKind,
    StreamSchedule,
    StreamScheduleOccurrenceException,
    StreamScheduleSegment,
    StreamScheduleSettings,
    TwitchScheduleOccurrenceState,
)


def _schedule(**overrides) -> StreamSchedule:
    values = {
        "id": 7,
        "channel_id": "channel-1",
        "kind": ScheduleKind.RECURRING,
        "weekday": 2,
        "specific_date": None,
        "start_time": time(20, 0),
        "duration_minutes": 120,
        "enabled": True,
    }
    values.update(overrides)
    return StreamSchedule(**values)


def _opening(**overrides) -> StreamScheduleSegment:
    values = {
        "id": 11,
        "channel_id": "channel-1",
        "schedule_id": 7,
        "offset_minutes": 0,
        "title_template": "晚間直播",
        "game_id": "509658",
        "game_name": "Just Chatting",
    }
    values.update(overrides)
    return StreamScheduleSegment(**values)


def _state(**overrides) -> TwitchSchedulePublishState:
    values = {
        "id": 1,
        "channel_id": "channel-1",
        "schedule_id": 7,
        "twitch_segment_id": "remote-1",
        "schedule_kind": ScheduleKind.RECURRING,
        "identity_key": "recurring:2:20:00:Asia/Taipei",
        "payload_fingerprint": "old",
        "status": "synced",
    }
    values.update(overrides)
    return TwitchSchedulePublishState(**values)


def _publisher():
    schedule_repo = MagicMock()
    publish_repo = MagicMock()
    channel_repo = MagicMock()
    twitch = MagicMock()
    publisher = StreamSchedulePublisher(
        schedule_repo,
        publish_repo,
        channel_repo,
        twitch,
        now=lambda: datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
    )
    token = Token(
        user_id="channel-1",
        token="secret",
        refresh="refresh",
        scopes="channel:manage:schedule",
    )
    return publisher, schedule_repo, publish_repo, twitch, token


def test_recurring_payload_uses_next_local_occurrence_and_opening_segment_only() -> None:
    payload = build_publish_payload(
        _schedule(),
        _opening(),
        timezone="Asia/Taipei",
        now_utc=datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
    )

    assert payload is not None
    assert payload.start_time == "2026-09-30T12:00:00Z"
    assert payload.identity_key == "recurring:2:20:00:Asia/Taipei"
    assert payload.is_recurring is True
    assert payload.title == "晚間直播"
    assert payload.category_id == "509658"
    assert payload.duration_minutes == 120


def test_one_off_that_has_ended_is_not_published() -> None:
    payload = build_publish_payload(
        _schedule(
            kind=ScheduleKind.ONE_OFF,
            weekday=None,
            specific_date=date(2026, 9, 28),
            start_time=time(20, 0),
            duration_minutes=60,
        ),
        _opening(),
        timezone="Asia/Taipei",
        now_utc=datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
    )

    assert payload is None


def test_active_one_off_payload_uses_its_exact_date() -> None:
    payload = build_publish_payload(
        _schedule(
            kind=ScheduleKind.ONE_OFF,
            weekday=None,
            specific_date=date(2026, 10, 2),
            start_time=time(20, 0),
        ),
        _opening(),
        timezone="Asia/Taipei",
        now_utc=datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
    )

    assert payload is not None
    assert payload.start_time == "2026-10-02T12:00:00Z"
    assert payload.identity_key.startswith("one_off:")
    assert payload.is_recurring is False


def test_publish_action_recreates_recurring_series_when_wall_clock_identity_changes() -> None:
    payload = build_publish_payload(
        _schedule(start_time=time(21, 0)),
        _opening(),
        timezone="Asia/Taipei",
        now_utc=datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
    )
    state = TwitchSchedulePublishState(
        id=1,
        channel_id="channel-1",
        schedule_id=7,
        twitch_segment_id="remote-1",
        schedule_kind=ScheduleKind.RECURRING,
        identity_key="recurring:2:20:00:Asia/Taipei",
        payload_fingerprint="old",
        status="synced",
    )

    assert payload is not None
    assert (
        decide_publish_action(enabled=True, payload=payload, state=state) is PublishAction.RECREATE
    )


def test_publish_action_updates_metadata_but_does_not_recreate_same_series() -> None:
    payload = build_publish_payload(
        _schedule(),
        _opening(title_template="新標題"),
        timezone="Asia/Taipei",
        now_utc=datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
    )
    state = TwitchSchedulePublishState(
        id=1,
        channel_id="channel-1",
        schedule_id=7,
        twitch_segment_id="remote-1",
        schedule_kind=ScheduleKind.RECURRING,
        identity_key=payload.identity_key if payload else "",
        payload_fingerprint="old",
        status="synced",
    )

    assert payload is not None
    assert decide_publish_action(enabled=True, payload=payload, state=state) is PublishAction.UPDATE


def test_publish_action_deletes_remote_when_local_schedule_is_disabled() -> None:
    state = TwitchSchedulePublishState(
        id=1,
        channel_id="channel-1",
        schedule_id=7,
        twitch_segment_id="remote-1",
        schedule_kind=ScheduleKind.RECURRING,
        identity_key="recurring:2:20:00:Asia/Taipei",
        payload_fingerprint="old",
        status="synced",
    )

    assert decide_publish_action(enabled=False, payload=None, state=state) is PublishAction.DELETE


def test_publish_action_is_noop_for_matching_state_or_unpublished_disabled_schedule() -> None:
    payload = build_publish_payload(
        _schedule(),
        _opening(),
        timezone="Asia/Taipei",
        now_utc=datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
    )
    assert payload is not None

    assert (
        decide_publish_action(
            enabled=True,
            payload=payload,
            state=_state(payload_fingerprint=payload.fingerprint),
        )
        is PublishAction.NONE
    )
    assert decide_publish_action(enabled=False, payload=None, state=None) is PublishAction.NONE


def test_remote_recovery_requires_matching_metadata_and_duration() -> None:
    payload = build_publish_payload(
        _schedule(),
        _opening(),
        timezone="Asia/Taipei",
        now_utc=datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
    )
    assert payload is not None
    remote = {
        "start_time": payload.start_time,
        "end_time": "2026-09-30T14:00:00Z",
        "title": "晚間直播",
        "category": {"id": "509658"},
    }

    assert StreamSchedulePublisher._remote_metadata_matches(remote, payload) is True
    assert (
        StreamSchedulePublisher._remote_metadata_matches({**remote, "title": "其他直播"}, payload)
        is False
    )
    assert StreamSchedulePublisher._remote_metadata_matches({"title": "晚間直播"}, payload) is False


async def test_sync_schedule_deletes_disabled_remote_and_recreates_changed_series() -> None:
    publisher, _, publish_repo, twitch, token = _publisher()
    publish_repo.delete_state = AsyncMock()
    publish_repo.mark_state_synced = AsyncMock()
    twitch.delete_channel_stream_schedule_segment = AsyncMock()
    twitch.get_channel_stream_schedule = AsyncMock(return_value=[])
    twitch.create_channel_stream_schedule_segment = AsyncMock(return_value={"id": "remote-2"})

    await publisher._sync_schedule("channel-1", token, _schedule(enabled=False), None, _state())

    publish_repo.delete_state.assert_awaited_once_with("channel-1", 1)

    payload = build_publish_payload(
        _schedule(start_time=time(21, 0)),
        _opening(),
        timezone="Asia/Taipei",
        now_utc=datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
    )
    assert payload is not None
    await publisher._sync_schedule(
        "channel-1", token, _schedule(start_time=time(21, 0)), payload, _state()
    )

    assert twitch.delete_channel_stream_schedule_segment.await_count == 2
    assert publish_repo.mark_state_synced.await_args.kwargs["twitch_segment_id"] == "remote-2"


async def test_sync_schedule_refreshes_remote_id_before_metadata_update() -> None:
    publisher, _, publish_repo, twitch, token = _publisher()
    payload = build_publish_payload(
        _schedule(),
        _opening(title_template="新標題"),
        timezone="Asia/Taipei",
        now_utc=datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
    )
    assert payload is not None
    twitch.get_channel_stream_schedule = AsyncMock(
        return_value=[
            {
                "id": "current-occurrence",
                "start_time": payload.start_time,
                "is_recurring": True,
            }
        ]
    )
    twitch.update_channel_stream_schedule_segment = AsyncMock(
        return_value={"id": "current-occurrence"}
    )
    publish_repo.mark_state_synced = AsyncMock()

    await publisher._sync_schedule("channel-1", token, _schedule(), payload, _state())

    twitch.update_channel_stream_schedule_segment.assert_awaited_once()
    assert twitch.update_channel_stream_schedule_segment.await_args.args[1] == "current-occurrence"


async def test_sync_schedule_persists_blocked_error_and_raises_retryable_failure() -> None:
    publisher, _, publish_repo, twitch, token = _publisher()
    payload = build_publish_payload(
        _schedule(),
        _opening(),
        timezone="Asia/Taipei",
        now_utc=datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
    )
    assert payload is not None
    publish_repo.mark_state_error = AsyncMock()
    twitch.get_channel_stream_schedule = AsyncMock(return_value=[])
    twitch.create_channel_stream_schedule_segment = AsyncMock(
        side_effect=TwitchScheduleAPIError("invalid_request", status_code=400, retryable=False)
    )

    await publisher._sync_schedule("channel-1", token, _schedule(), payload, None)

    assert publish_repo.mark_state_error.await_args.kwargs["blocked"] is True

    twitch.create_channel_stream_schedule_segment.side_effect = TwitchScheduleAPIError(
        "provider_unavailable", status_code=503, retryable=True
    )
    with pytest.raises(StreamSchedulePublisherError, match="provider_unavailable"):
        await publisher._sync_schedule("channel-1", token, _schedule(), payload, None)


async def test_delete_orphan_treats_stale_remote_as_already_removed() -> None:
    publisher, _, publish_repo, twitch, token = _publisher()
    twitch.delete_channel_stream_schedule_segment = AsyncMock(
        side_effect=TwitchScheduleAPIError("segment_not_found", status_code=400, retryable=False)
    )
    publish_repo.delete_state = AsyncMock()

    await publisher._delete_orphan("channel-1", token, _state(schedule_id=None))

    publish_repo.delete_state.assert_awaited_once_with("channel-1", 1)


async def test_delete_orphan_surfaces_non_retryable_provider_rejection() -> None:
    publisher, _, publish_repo, twitch, token = _publisher()
    twitch.delete_channel_stream_schedule_segment = AsyncMock(
        side_effect=TwitchScheduleAPIError("unauthorized", status_code=401, retryable=False)
    )
    publish_repo.mark_existing_state_error = AsyncMock()

    await publisher._delete_orphan("channel-1", token, _state(schedule_id=None))

    publish_repo.mark_existing_state_error.assert_awaited_once_with(
        "channel-1", 1, error_code="unauthorized", blocked=True
    )


async def test_sync_channel_blocks_only_schedule_publication_when_scope_is_missing() -> None:
    schedule_repo = MagicMock()
    schedule_repo.get_or_create_settings = AsyncMock(
        return_value=StreamScheduleSettings(channel_id="channel-1", timezone="Asia/Taipei")
    )
    schedule_repo.list_all = AsyncMock(return_value=[_schedule()])
    schedule_repo.list_segments_for_schedules = AsyncMock(return_value={7: [_opening()]})
    schedule_repo.list_occurrence_exceptions = AsyncMock(return_value=[])
    publish_repo = MagicMock()
    publish_repo.list_states = AsyncMock(return_value=[])
    publish_repo.mark_state_error = AsyncMock()
    channel_repo = MagicMock()
    channel_repo.get_token = AsyncMock(
        return_value=Token(
            user_id="channel-1",
            token="secret",
            refresh="refresh",
            scopes="channel:bot channel:manage:broadcast",
        )
    )
    twitch = MagicMock()
    twitch.create_channel_stream_schedule_segment = AsyncMock()

    await StreamSchedulePublisher(
        schedule_repo,
        publish_repo,
        channel_repo,
        twitch,
        now=lambda: datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
    ).sync_channel("channel-1")

    publish_repo.mark_state_error.assert_awaited_once_with(
        "channel-1",
        schedule_id=7,
        schedule_kind=ScheduleKind.RECURRING,
        error_code="missing_scope",
        blocked=True,
    )
    twitch.create_channel_stream_schedule_segment.assert_not_awaited()


async def test_sync_channel_creates_one_remote_segment_from_opening_metadata() -> None:
    schedule_repo = MagicMock()
    schedule_repo.get_or_create_settings = AsyncMock(
        return_value=StreamScheduleSettings(channel_id="channel-1", timezone="Asia/Taipei")
    )
    schedule_repo.list_all = AsyncMock(return_value=[_schedule()])
    schedule_repo.list_segments_for_schedules = AsyncMock(return_value={7: [_opening()]})
    schedule_repo.list_occurrence_exceptions = AsyncMock(return_value=[])
    publish_repo = MagicMock()
    publish_repo.list_states = AsyncMock(return_value=[])
    publish_repo.list_occurrence_states = AsyncMock(return_value=[])
    publish_repo.mark_state_synced = AsyncMock()
    channel_repo = MagicMock()
    channel_repo.get_token = AsyncMock(
        return_value=Token(
            user_id="channel-1",
            token="secret",
            refresh="refresh",
            scopes="channel:bot channel:manage:schedule",
        )
    )
    twitch = MagicMock()
    twitch.get_channel_stream_schedule = AsyncMock(return_value=[])
    twitch.create_channel_stream_schedule_segment = AsyncMock(return_value={"id": "remote-1"})

    await StreamSchedulePublisher(
        schedule_repo,
        publish_repo,
        channel_repo,
        twitch,
        now=lambda: datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
    ).sync_channel("channel-1")

    twitch.create_channel_stream_schedule_segment.assert_awaited_once_with(
        "channel-1",
        "secret",
        start_time="2026-09-30T12:00:00Z",
        timezone="Asia/Taipei",
        duration_minutes=120,
        is_recurring=True,
        title="晚間直播",
        category_id="509658",
    )
    assert publish_repo.mark_state_synced.await_args.kwargs["twitch_segment_id"] == "remote-1"


async def test_new_series_can_cancel_its_next_occurrence_in_the_same_job() -> None:
    schedule_repo = MagicMock()
    schedule_repo.get_or_create_settings = AsyncMock(
        return_value=StreamScheduleSettings(channel_id="channel-1", timezone="Asia/Taipei")
    )
    schedule_repo.list_all = AsyncMock(return_value=[_schedule()])
    schedule_repo.list_segments_for_schedules = AsyncMock(return_value={7: [_opening()]})
    schedule_repo.list_occurrence_exceptions = AsyncMock(
        return_value=[
            StreamScheduleOccurrenceException(
                id=21,
                channel_id="channel-1",
                recurring_schedule_id=7,
                occurrence_date=date(2026, 9, 30),
                kind=OccurrenceExceptionKind.CANCELLED,
            )
        ]
    )
    series_state = TwitchSchedulePublishState(
        id=1,
        channel_id="channel-1",
        schedule_id=7,
        twitch_segment_id="remote-series",
        schedule_kind=ScheduleKind.RECURRING,
        identity_key="recurring:2:20:00:Asia/Taipei",
        payload_fingerprint="current",
        status="synced",
    )
    occurrence_state = TwitchScheduleOccurrenceState(
        id=31,
        channel_id="channel-1",
        recurring_schedule_id=7,
        occurrence_date=date(2026, 9, 30),
        twitch_segment_id=None,
        desired_state="cancelled",
        status="pending",
    )
    publish_repo = MagicMock()
    publish_repo.list_states = AsyncMock(side_effect=[[], [series_state]])
    publish_repo.mark_state_synced = AsyncMock()
    publish_repo.list_occurrence_states = AsyncMock(return_value=[])
    publish_repo.upsert_occurrence_desired = AsyncMock(return_value=occurrence_state)
    publish_repo.mark_occurrence_status = AsyncMock()
    channel_repo = MagicMock()
    channel_repo.get_token = AsyncMock(
        return_value=Token(
            user_id="channel-1",
            token="secret",
            refresh="refresh",
            scopes="channel:manage:schedule",
        )
    )
    twitch = MagicMock()
    twitch.get_channel_stream_schedule = AsyncMock(
        side_effect=[
            [],
            [
                {
                    "id": "occurrence-1",
                    "start_time": "2026-09-30T12:00:00Z",
                    "is_recurring": True,
                }
            ],
        ]
    )
    twitch.create_channel_stream_schedule_segment = AsyncMock(return_value={"id": "remote-series"})
    twitch.update_channel_stream_schedule_segment = AsyncMock(return_value={"id": "occurrence-1"})

    deferred = await StreamSchedulePublisher(
        schedule_repo,
        publish_repo,
        channel_repo,
        twitch,
        now=lambda: datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
    ).sync_channel("channel-1")

    assert deferred is False
    twitch.update_channel_stream_schedule_segment.assert_awaited_once_with(
        "channel-1", "occurrence-1", "secret", is_canceled=True
    )
