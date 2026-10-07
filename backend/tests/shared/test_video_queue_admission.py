import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared.models.video_queue import VideoQueueEntry
from shared.services.video_queue_admission import (
    ADMISSION_POLICIES,
    CHAT_ACTOR_POLICIES,
    AdmissionReason,
    AdmissionRejected,
    VideoQueueAdmissionService,
    policy_for,
)
from shared.video_sources import ResolvedVideo, VideoMetadata


def _settings(**overrides):
    values = {
        "enabled": True,
        "redemption_enabled": True,
        "max_duration_redemption": 600,
        "max_queue_size": 20,
        "min_view_count": 0,
        "user_cooldown_seconds": 0,
        "max_per_user": 0,
        "max_duration_seconds": 0,
        "replay_cooldown_hours": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _entry(source: str) -> VideoQueueEntry:
    return VideoQueueEntry(
        id=1,
        channel_id="ch1",
        video_id="dQw4w9WgXcQ",
        requested_by="viewer",
        source=source,
        status="queued",
    )


def _service(settings=None):
    queue = SimpleNamespace(
        video_is_active=AsyncMock(return_value=False),
        get_queue_size=AsyncMock(return_value=0),
        count_active_by_user=AsyncMock(return_value=0),
        find_last_entry_by_user=AsyncMock(return_value=None),
        played_within=AsyncMock(return_value=False),
        add_if_within_limits=AsyncMock(side_effect=lambda **kw: _entry(kw["source"])),
        add=AsyncMock(side_effect=lambda **kw: _entry(kw["source"])),
        get_queue_position=AsyncMock(return_value=4),
    )
    settings_repo = SimpleNamespace(get_or_create=AsyncMock(return_value=settings or _settings()))
    blocklist = SimpleNamespace(check=AsyncMock(return_value=None))
    return VideoQueueAdmissionService(queue, settings_repo, blocklist), queue, blocklist


async def _resolve(_url: str):
    return ResolvedVideo("youtube", "dQw4w9WgXcQ")


async def _metadata(_resolved: ResolvedVideo):
    return VideoMetadata("Title", 120, 1_000, False)


def test_source_policy_matrix_is_explicit():
    assert ADMISSION_POLICIES["chat"].enforce_user_limits is True
    assert ADMISSION_POLICIES["redemption"].source_duration_field == "max_duration_redemption"
    assert ADMISSION_POLICIES["donation"].enforce_queue_size is True
    assert ADMISSION_POLICIES["dashboard"].enforce_queue_size is False
    assert ADMISSION_POLICIES["dashboard"].enforce_min_views is False
    assert ADMISSION_POLICIES["dashboard"].enforce_replay_cooldown is False


def test_chat_actor_policy_matrix_is_explicit():
    viewer, mod, broadcaster = (
        CHAT_ACTOR_POLICIES["viewer"],
        CHAT_ACTOR_POLICIES["moderator"],
        CHAT_ACTOR_POLICIES["broadcaster"],
    )
    assert viewer is ADMISSION_POLICIES["chat"]
    # Mods: no audience-fairness gates, but capacity holds and no queue jumping.
    assert mod.enforce_queue_size is True
    assert not (mod.enforce_user_limits or mod.enforce_min_views or mod.enforce_replay_cooldown)
    assert mod.priority is None
    # Broadcaster: same trust and tier as a dashboard add.
    assert not broadcaster.enforce_queue_size
    assert broadcaster.priority == 30


def test_actor_only_applies_to_chat():
    assert policy_for("redemption") is ADMISSION_POLICIES["redemption"]
    with pytest.raises(ValueError):
        policy_for("redemption", "moderator")


@pytest.mark.asyncio
async def test_moderator_chat_skips_fairness_gates_but_keeps_capacity():
    settings = _settings(
        min_view_count=10_000, max_per_user=1, user_cooldown_seconds=60, replay_cooldown_hours=6
    )
    service, queue, blocklist = _service(settings)
    queue.count_active_by_user.return_value = 3
    queue.played_within.return_value = True

    result = await service.admit(
        channel_id="ch1",
        url="https://youtu.be/dQw4w9WgXcQ",
        requested_by="mod",
        requested_by_id="m1",
        source="chat",
        actor="moderator",
        resolve=_resolve,
        fetch_metadata=_metadata,  # 1,000 views < 10,000
    )

    kwargs = queue.add_if_within_limits.await_args.kwargs
    assert kwargs["max_per_user"] == 0
    assert kwargs["priority"] == 0
    assert kwargs["max_queue_size"] == 20
    # The requester-scoped blocklist rule is a fairness gate, not a content gate.
    assert blocklist.check.await_args.kwargs["requested_by"] is None
    assert result.position == 4

    queue.get_queue_size.return_value = 20
    with pytest.raises(AdmissionRejected) as exc_info:
        await service.admit(
            channel_id="ch1",
            url="https://youtu.be/dQw4w9WgXcQ",
            requested_by="mod",
            source="chat",
            actor="moderator",
            resolve=_resolve,
            fetch_metadata=_metadata,
        )
    assert exc_info.value.reason is AdmissionReason.QUEUE_FULL


@pytest.mark.asyncio
async def test_broadcaster_chat_is_treated_like_a_dashboard_add():
    service, queue, _ = _service(_settings(max_queue_size=1))
    queue.get_queue_size.return_value = 1

    result = await service.admit(
        channel_id="ch1",
        url="https://youtu.be/dQw4w9WgXcQ",
        requested_by="streamer",
        source="chat",
        actor="broadcaster",
        resolve=_resolve,
        fetch_metadata=_metadata,
    )

    queue.add.assert_awaited_once()
    assert queue.add.await_args.kwargs["priority"] == 30
    assert queue.add.await_args.kwargs["source"] == "chat"
    assert result.position == 4


@pytest.mark.asyncio
async def test_dashboard_does_not_look_up_a_position():
    service, queue, _ = _service()

    result = await service.admit(
        channel_id="ch1",
        url="https://youtu.be/dQw4w9WgXcQ",
        requested_by="streamer",
        source="dashboard",
        resolve=_resolve,
        fetch_metadata=_metadata,
    )

    assert result.position is None
    queue.get_queue_position.assert_not_awaited()


@pytest.mark.asyncio
async def test_dashboard_bypasses_capacity_but_donation_does_not():
    service, queue, _ = _service(_settings(max_queue_size=1))
    queue.get_queue_size.return_value = 1

    dashboard = await service.admit(
        channel_id="ch1",
        url="https://youtu.be/dQw4w9WgXcQ",
        requested_by="streamer",
        source="dashboard",
        resolve=_resolve,
        fetch_metadata=_metadata,
    )
    assert dashboard.entry.source == "dashboard"
    queue.add.assert_awaited_once()

    with pytest.raises(AdmissionRejected) as exc_info:
        await service.admit(
            channel_id="ch1",
            url="https://youtu.be/dQw4w9WgXcQ",
            requested_by="donor",
            source="donation",
            resolve=_resolve,
            fetch_metadata=_metadata,
        )
    assert exc_info.value.reason is AdmissionReason.QUEUE_FULL


@pytest.mark.asyncio
async def test_redemption_uses_stricter_source_or_global_duration_limit():
    service, queue, _ = _service(_settings(max_duration_redemption=600, max_duration_seconds=300))

    async def long_metadata(_resolved: ResolvedVideo):
        return VideoMetadata("Long", 301, 1_000, False)

    with pytest.raises(AdmissionRejected) as exc_info:
        await service.admit(
            channel_id="ch1",
            url="https://youtu.be/dQw4w9WgXcQ",
            requested_by="viewer",
            requested_by_id="u1",
            source="redemption",
            resolve=_resolve,
            fetch_metadata=long_metadata,
        )

    assert exc_info.value.reason is AdmissionReason.TOO_LONG
    assert exc_info.value.details["limit_seconds"] == 300
    queue.add_if_within_limits.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_cooldown_is_centralized():
    service, queue, _ = _service(_settings(user_cooldown_seconds=60))
    queue.find_last_entry_by_user.return_value = SimpleNamespace(created_at=datetime.now(UTC))

    with pytest.raises(AdmissionRejected) as exc_info:
        await service.admit(
            channel_id="ch1",
            url="https://youtu.be/dQw4w9WgXcQ",
            requested_by="viewer",
            requested_by_id="u1",
            source="chat",
            resolve=_resolve,
            fetch_metadata=_metadata,
        )

    assert exc_info.value.reason is AdmissionReason.USER_COOLDOWN
    assert 0 <= exc_info.value.details["remaining_seconds"] <= 60


@pytest.mark.asyncio
async def test_donation_uses_common_playability_and_blocklist_gates():
    service, queue, blocklist = _service()

    async def unplayable(_resolved: ResolvedVideo):
        return VideoMetadata("Private", 120, 1_000, False, playable=False)

    with pytest.raises(AdmissionRejected) as exc_info:
        await service.admit(
            channel_id="ch1",
            url="https://youtu.be/dQw4w9WgXcQ",
            requested_by="donor",
            source="donation",
            resolve=_resolve,
            fetch_metadata=unplayable,
        )
    assert exc_info.value.reason is AdmissionReason.NOT_PLAYABLE
    blocklist.check.assert_not_awaited()
    queue.add_if_within_limits.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_and_replay_checks_include_provider_identity():
    service, queue, _ = _service(_settings(replay_cooldown_hours=12))

    await service.admit(
        channel_id="ch1",
        url="https://youtu.be/dQw4w9WgXcQ",
        requested_by="viewer",
        source="chat",
        resolve=_resolve,
        fetch_metadata=_metadata,
    )

    queue.video_is_active.assert_awaited_once_with("ch1", "dQw4w9WgXcQ", "youtube")
    queue.played_within.assert_awaited_once_with("ch1", "dQw4w9WgXcQ", 12, "youtube")


@pytest.mark.asyncio
async def test_admission_logs_outcome_without_copying_submitted_url(caplog):
    service, queue, _ = _service()
    submitted_url = "https://youtu.be/dQw4w9WgXcQ?private-query=secret"

    with caplog.at_level(logging.INFO, logger="shared.services.video_queue_admission"):
        await service.admit(
            channel_id="ch1",
            url=submitted_url,
            requested_by="viewer",
            source="chat",
            resolve=_resolve,
            fetch_metadata=_metadata,
        )

    assert "video_queue_admission_accepted" in caplog.text
    assert submitted_url not in caplog.text
    assert queue.add_if_within_limits.await_count == 1


async def _admit_youtube(service, url: str, *, length: int = 300, source: str = "dashboard"):
    async def metadata(_resolved: ResolvedVideo):
        return VideoMetadata("Title", length, 1_000, False)

    return await service.admit(
        channel_id="ch1",
        url=url,
        requested_by="viewer",
        requested_by_id="u1",
        source=source,
        resolve=_resolve,
        fetch_metadata=metadata,
    )


@pytest.mark.asyncio
async def test_typed_segment_is_stored_as_start_and_length():
    service, queue, _ = _service()
    await _admit_youtube(service, "https://youtu.be/dQw4w9WgXcQ 1:30-4:00")
    kwargs = queue.add.await_args.kwargs
    assert kwargs["start_seconds"] == 90
    assert kwargs["duration_seconds"] == 150


@pytest.mark.asyncio
async def test_length_limit_checks_the_segment_not_the_video():
    service, queue, _ = _service(_settings(max_duration_seconds=600))
    await _admit_youtube(service, "https://youtu.be/dQw4w9WgXcQ 10:00-15:00", length=3600)
    assert queue.add.await_args.kwargs["duration_seconds"] == 300

    with pytest.raises(AdmissionRejected) as exc_info:
        await _admit_youtube(service, "https://youtu.be/dQw4w9WgXcQ 10:00-25:00", length=3600)
    assert exc_info.value.reason is AdmissionReason.TOO_LONG
    assert exc_info.value.details["segment"] == 1


@pytest.mark.asyncio
async def test_too_long_whole_video_is_still_rejected_with_a_segment_hint():
    service, queue, _ = _service(_settings(max_duration_seconds=600))
    with pytest.raises(AdmissionRejected) as exc_info:
        await _admit_youtube(service, "https://youtu.be/dQw4w9WgXcQ", length=3600)
    assert exc_info.value.reason is AdmissionReason.TOO_LONG
    assert exc_info.value.details["segment"] == 0
    queue.add.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("suffix", "code"),
    [
        ("90", "format"),
        ("4:00-1:30", "order"),
        ("1:30-6:00", "out_of_range"),
        ("1:30-1:35", "too_short"),
    ],
)
async def test_segment_errors_reject_before_insert(suffix, code):
    service, queue, _ = _service()
    with pytest.raises(AdmissionRejected) as exc_info:
        await _admit_youtube(service, f"https://youtu.be/dQw4w9WgXcQ {suffix}")
    assert exc_info.value.reason is AdmissionReason.INVALID_SEGMENT
    assert exc_info.value.details == {"segment_error": code}
    queue.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsupported_url_wins_over_a_bad_time():
    service, _, _ = _service()

    async def unresolved(_url: str):
        return None

    with pytest.raises(AdmissionRejected) as exc_info:
        await service.admit(
            channel_id="ch1",
            url="https://example.com/x 90",
            requested_by="viewer",
            source="dashboard",
            resolve=unresolved,
            fetch_metadata=_metadata,
        )
    assert exc_info.value.reason is AdmissionReason.INVALID_URL


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", ["0:10-0:20", "90"])
async def test_clip_ignores_a_typed_time(suffix):
    service, queue, _ = _service()

    async def clip(_url: str):
        return ResolvedVideo("twitch_clip", "Slug")

    await service.admit(
        channel_id="ch1",
        url=f"https://clips.twitch.tv/Slug {suffix}",
        requested_by="viewer",
        source="dashboard",
        resolve=clip,
        fetch_metadata=lambda _r: _metadata(_r),
    )
    kwargs = queue.add.await_args.kwargs
    assert (kwargs["start_seconds"], kwargs["duration_seconds"]) == (0, 120)


@pytest.mark.asyncio
async def test_twitch_channel_link_is_rejected_with_a_vod_hint():
    service, _, _ = _service()

    async def unresolved(_url: str):
        return None

    with pytest.raises(AdmissionRejected) as exc_info:
        await service.admit(
            channel_id="ch1",
            url="https://www.twitch.tv/somestreamer",
            requested_by="viewer",
            source="dashboard",
            resolve=unresolved,
            fetch_metadata=_metadata,
        )
    assert exc_info.value.reason is AdmissionReason.INVALID_URL
    assert exc_info.value.details == {"hint": "twitch_channel"}


@pytest.mark.asyncio
async def test_youtube_with_no_data_is_rejected_even_without_a_length_limit():
    """API failure / quota: live status is unknown, and a live stream let in
    plays forever. The dashboard (no limit) used to let this through."""
    service, queue, _ = _service()

    async def nothing(_resolved: ResolvedVideo):
        return VideoMetadata(None, None, None, False)

    with pytest.raises(AdmissionRejected) as exc_info:
        await service.admit(
            channel_id="ch1",
            url="https://youtu.be/dQw4w9WgXcQ",
            requested_by="viewer",
            source="dashboard",
            resolve=_resolve,
            fetch_metadata=nothing,
        )
    assert exc_info.value.reason is AdmissionReason.METADATA_UNVERIFIABLE
    assert exc_info.value.details == {"field": "youtube"}
    queue.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_blocked_rejection_carries_the_rule_kind():
    service, _, blocklist = _service()
    blocklist.check = AsyncMock(return_value=SimpleNamespace(kind="creator"))
    with pytest.raises(AdmissionRejected) as exc_info:
        await _admit_youtube(service, "https://youtu.be/dQw4w9WgXcQ")
    assert exc_info.value.reason is AdmissionReason.BLOCKED
    assert exc_info.value.details == {"blocked_kind": "creator"}
