import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared.models.video_queue import VideoQueueEntry
from shared.services.video_queue_admission import (
    ADMISSION_POLICIES,
    AdmissionReason,
    AdmissionRejected,
    VideoQueueAdmissionService,
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
