"""Contracts for the process-level Live Display update hub and SSE frames."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import Request

import services.community_overlay_stream as stream_module
from routers.community_overlay_router import stream_public_overlay
from services.community_overlay_stream import OverlayCapacityError, OverlayUpdateHub, encode_sse
from shared.community_overlay_themes import DEFAULT_OVERLAY_THEME
from shared.models.attendance import (
    CommunityOverlayEvent,
    CommunityOverlaySnapshot,
    CommunityOverlayThemePublished,
)


def test_sse_frame_is_named_json_and_cannot_inject_lines() -> None:
    frame = encode_sse("update", {"channel": "line1\nline2", "cursor": 12})

    assert frame.startswith("event: update\n")
    assert frame.endswith("\n\n")
    assert (
        "data: " + json.dumps({"channel": "line1\nline2", "cursor": 12}, separators=(",", ":"))
        in frame
    )
    assert frame.count("data: ") == 1


@pytest.mark.asyncio
async def test_one_hub_fans_out_and_coalesces_slow_consumers() -> None:
    hub = OverlayUpdateHub("postgresql://test:test@localhost/test", queue_size=1)
    first = hub.subscribe("channel-1")
    second = hub.subscribe("channel-1")
    other = hub.subscribe("channel-2")

    hub.notify("channel-1")
    hub.notify("channel-1")

    await asyncio.wait_for(first.wait(), timeout=0.1)
    await asyncio.wait_for(second.wait(), timeout=0.1)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(other.wait(), timeout=0.01)

    first.close()
    second.close()
    other.close()
    assert hub.subscriber_count == 0


def test_hub_bounds_concurrent_subscribers_per_channel_and_process() -> None:
    hub = OverlayUpdateHub(
        "postgresql://test:test@localhost/test",
        max_subscribers_per_channel=2,
        max_subscribers=3,
    )
    subscriptions = [
        hub.subscribe("channel-1"),
        hub.subscribe("channel-1"),
        hub.subscribe("channel-2"),
    ]

    with pytest.raises(OverlayCapacityError):
        hub.subscribe("channel-1")
    with pytest.raises(OverlayCapacityError):
        hub.subscribe("channel-3")

    for subscription in subscriptions:
        subscription.close()


@pytest.mark.asyncio
async def test_reconnect_wakes_every_subscriber_for_cursor_replay() -> None:
    hub = OverlayUpdateHub("postgresql://test:test@localhost/test")
    first = hub.subscribe("channel-1")
    second = hub.subscribe("channel-2")

    hub.notify_all()

    await asyncio.wait_for(first.wait(), timeout=0.1)
    await asyncio.wait_for(second.wait(), timeout=0.1)
    first.close()
    second.close()


@pytest.mark.asyncio
async def test_listener_uses_one_connection_and_reconnects_with_replay_wake(monkeypatch) -> None:
    drop_listener = asyncio.Event()

    async def fail_keepalive_after_first_wake(_query: str) -> None:
        await drop_listener.wait()
        raise ConnectionError("listener dropped")

    first_connection = AsyncMock()
    first_connection.execute.side_effect = fail_keepalive_after_first_wake
    second_connection = AsyncMock()
    connect = AsyncMock(side_effect=[first_connection, second_connection])
    monkeypatch.setattr(stream_module.asyncpg, "connect", connect)
    hub = OverlayUpdateHub(
        "postgresql://test:test@localhost/test",
        keepalive_seconds=0.01,
        reconnect_initial_seconds=0.01,
    )
    subscription = hub.subscribe("channel-1")

    hub.start()
    hub.start()
    try:
        await asyncio.wait_for(subscription.wait(), timeout=0.2)
        drop_listener.set()
        await asyncio.wait_for(subscription.wait(), timeout=1.0)

        assert connect.await_count == 2
        first_connection.add_listener.assert_awaited_once()
        second_connection.add_listener.assert_awaited_once()
    finally:
        await hub.stop()
        subscription.close()


@pytest.mark.asyncio
async def test_invalid_notification_does_not_wake_subscribers() -> None:
    hub = OverlayUpdateHub("postgresql://test:test@localhost/test")
    subscription = hub.subscribe("channel-1")

    hub._on_notification(MagicMock(), 1, "community_overlay_updates", "not-json")

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(subscription.wait(), timeout=0.01)
    subscription.close()


@pytest.mark.asyncio
async def test_stream_route_releases_capacity_when_initial_snapshot_fails() -> None:
    service = MagicMock()
    service.resolve_public_channel = AsyncMock(return_value="channel-1")
    service.get_stream_snapshot = AsyncMock(side_effect=RuntimeError("database unavailable"))
    hub = OverlayUpdateHub(
        "postgresql://test:test@localhost/test",
        max_subscribers_per_channel=1,
        max_subscribers=1,
    )
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
    hub = OverlayUpdateHub("postgresql://test:test@localhost/test")
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
    hub = OverlayUpdateHub("postgresql://test:test@localhost/test")
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
