"""The Live Display `/public/stream` route: snapshot/update framing, lease,
capacity, and cleanup. Generic NOTIFY-wake hub behaviour (fan-out, capacity,
reconnect, multi-channel routing) lives in test_notify_stream.py."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import Request

from core.dependencies import COMMUNITY_OVERLAY_NOTIFY_CHANNEL
from routers.community_overlay_router import stream_public_overlay
from services.notify_stream import NotifyWakeHub
from shared.community_overlay_themes import DEFAULT_OVERLAY_THEME
from shared.models.attendance import (
    CommunityOverlayEvent,
    CommunityOverlaySnapshot,
    CommunityOverlayThemePublished,
)


def _hub(**kwargs: object) -> NotifyWakeHub:
    return NotifyWakeHub(
        "postgresql://test:test@localhost/test",
        notify_channels=[COMMUNITY_OVERLAY_NOTIFY_CHANNEL],
        **kwargs,
    )


@pytest.mark.asyncio
async def test_stream_route_releases_capacity_when_initial_snapshot_fails() -> None:
    service = MagicMock()
    service.resolve_public_channel = AsyncMock(return_value="channel-1")
    service.get_stream_snapshot = AsyncMock(side_effect=RuntimeError("database unavailable"))
    hub = _hub(max_subscribers_per_channel=1, max_subscribers=1)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/live-display/public/stream",
            "headers": [],
            "client": ("127.0.0.2", 1234),
        }
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await stream_public_overlay(
            request=request,
            overlay_key=str(UUID("22222222-2222-4222-8222-222222222222")),
            after_id=None,
            service=service,
            hub=hub,
        )

    assert hub.subscriber_count == 0


@pytest.mark.asyncio
async def test_stream_route_hard_lease_releases_subscription(monkeypatch) -> None:
    monkeypatch.setattr("routers.community_overlay_router._STREAM_LEASE_SECONDS", 0.01)
    snapshot = CommunityOverlaySnapshot(
        channel_id="channel-lease",
        cursor=0,
        events=(),
        themes={},
    )
    service = MagicMock()
    service.resolve_public_channel = AsyncMock(return_value="channel-lease")
    service.get_stream_snapshot = AsyncMock(return_value=snapshot)
    hub = _hub()
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/live-display/public/stream",
            "headers": [],
            "client": ("127.0.0.3", 1234),
        }
    )

    response = await stream_public_overlay(
        request=request,
        overlay_key=str(UUID("33333333-3333-4333-8333-333333333333")),
        after_id=None,
        service=service,
        hub=hub,
    )
    await anext(response.body_iterator)
    assert hub.subscriber_count == 1

    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(response.body_iterator), timeout=0.1)

    assert hub.subscriber_count == 0


@pytest.mark.asyncio
async def test_stream_route_sends_protected_snapshot_and_cleans_up_disconnect() -> None:
    now = datetime(2026, 9, 2, tzinfo=UTC)
    first_event = CommunityOverlayEvent(
        id=7,
        channel_id="channel-1",
        event_type="checkin.recorded",
        schema_version=1,
        source="twitch",
        actor_user_id="private-id",
        actor_display_name="Alice",
        payload={"total_days": 3, "checkin_date": "2026-09-02"},
        occurred_at=now,
        expires_at=now + timedelta(minutes=10),
    )
    snapshot = CommunityOverlaySnapshot(
        channel_id="channel-1",
        cursor=7,
        events=tuple(first_event for _ in range(100)),
        themes={
            "checkin": CommunityOverlayThemePublished(
                revision_id=4,
                renderer="checkin-card",
                schema_version=1,
                theme=DEFAULT_OVERLAY_THEME,
                created_at=now,
            )
        },
    )
    service = MagicMock()
    service.resolve_public_channel = AsyncMock(return_value="channel-1")
    tail = CommunityOverlaySnapshot(
        channel_id="channel-1",
        cursor=8,
        events=(first_event,),
        themes=snapshot.themes,
    )
    service.get_stream_snapshot = AsyncMock(side_effect=[snapshot, tail])
    hub = _hub()
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/live-display/public/stream",
            "headers": [],
            "client": ("127.0.0.1", 1234),
        }
    )

    response = await stream_public_overlay(
        request=request,
        overlay_key=str(UUID("11111111-1111-4111-8111-111111111111")),
        after_id=None,
        service=service,
        hub=hub,
    )
    frame = await anext(response.body_iterator)
    await anext(response.body_iterator)

    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-store, no-transform"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-accel-buffering"] == "no"
    assert "private-id" not in frame
    assert '"cursor":7' in frame
    service.get_stream_snapshot.assert_any_await(
        UUID("11111111-1111-4111-8111-111111111111"), after_id=7
    )
    await response.body_iterator.aclose()
    assert hub.subscriber_count == 0
