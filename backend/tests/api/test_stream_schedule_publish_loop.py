from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from api.app import _stream_schedule_publish_loop

from services.stream_schedule_publisher import StreamSchedulePublisherError
from shared.models.stream_schedule import StreamSchedulePublishJob

_SETTINGS = SimpleNamespace(twitch_token_encryption_key="test-key")


async def test_publish_loop_completes_job_and_requeues_deferred_occurrences() -> None:
    db_manager = MagicMock(is_connected=True, pool=MagicMock())
    job = StreamSchedulePublishJob(channel_id="channel-1", generation=3, attempt_count=0)
    publish_repo = MagicMock()
    publish_repo.claim_due_job = AsyncMock(return_value=job)
    publish_repo.complete_job = AsyncMock()
    publish_repo.enqueue_deferred = AsyncMock()
    publisher = MagicMock()
    publisher.sync_channel = AsyncMock(return_value=True)

    with (
        patch("api.app.StreamSchedulePublishRepository", return_value=publish_repo),
        patch("api.app.StreamSchedulePublisher", return_value=publisher),
        patch("api.app.ChannelRepository"),
        patch("api.app.StreamScheduleRepository"),
        patch("api.app.get_twitch_api", return_value=MagicMock()),
        patch("api.app.asyncio.sleep", new=AsyncMock(side_effect=asyncio.CancelledError)) as sleep,
    ):
        await _stream_schedule_publish_loop(db_manager, _SETTINGS)

    publisher.sync_channel.assert_awaited_once_with("channel-1")
    publish_repo.complete_job.assert_awaited_once_with("channel-1", generation=3)
    publish_repo.enqueue_deferred.assert_awaited_once_with("channel-1", delay_seconds=3600)
    sleep.assert_awaited_once_with(1.0)


async def test_publish_loop_keeps_transient_failure_for_bounded_retry() -> None:
    db_manager = MagicMock(is_connected=True, pool=MagicMock())
    job = StreamSchedulePublishJob(channel_id="channel-1", generation=5, attempt_count=2)
    publish_repo = MagicMock()
    publish_repo.claim_due_job = AsyncMock(return_value=job)
    publish_repo.fail_job = AsyncMock()
    publisher = MagicMock()
    publisher.sync_channel = AsyncMock(
        side_effect=StreamSchedulePublisherError("provider_unavailable", retryable=True)
    )

    with (
        patch("api.app.StreamSchedulePublishRepository", return_value=publish_repo),
        patch("api.app.StreamSchedulePublisher", return_value=publisher),
        patch("api.app.ChannelRepository"),
        patch("api.app.StreamScheduleRepository"),
        patch("api.app.get_twitch_api", return_value=MagicMock()),
        patch("api.app.asyncio.sleep", new=AsyncMock(side_effect=asyncio.CancelledError)),
    ):
        await _stream_schedule_publish_loop(db_manager, _SETTINGS)

    publish_repo.fail_job.assert_awaited_once_with(
        "channel-1",
        generation=5,
        attempt_count=2,
        error_code="provider_unavailable",
        retryable=True,
    )
    publish_repo.complete_job.assert_not_called()
