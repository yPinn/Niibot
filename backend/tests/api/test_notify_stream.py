"""Generic NOTIFY-wake hub: multi-channel routing, fan-out, capacity, reconnect."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import services.notify_stream as stream_module
from services.notify_stream import NotifyWakeHub, StreamCapacityError, encode_sse

CHANNEL_A = "channel-a-updates"
CHANNEL_B = "channel-b-updates"


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
    hub = NotifyWakeHub(
        "postgresql://test:test@localhost/test",
        notify_channels=[CHANNEL_A],
        queue_size=1,
    )
    first = hub.subscribe(CHANNEL_A, "channel-1")
    second = hub.subscribe(CHANNEL_A, "channel-1")
    other = hub.subscribe(CHANNEL_A, "channel-2")

    hub.notify(CHANNEL_A, "channel-1")
    hub.notify(CHANNEL_A, "channel-1")

    await asyncio.wait_for(first.wait(), timeout=0.1)
    await asyncio.wait_for(second.wait(), timeout=0.1)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(other.wait(), timeout=0.01)

    first.close()
    second.close()
    other.close()
    assert hub.subscriber_count == 0


def test_hub_bounds_concurrent_subscribers_per_channel_and_process() -> None:
    hub = NotifyWakeHub(
        "postgresql://test:test@localhost/test",
        notify_channels=[CHANNEL_A],
        max_subscribers_per_channel=2,
        max_subscribers=3,
    )
    subscriptions = [
        hub.subscribe(CHANNEL_A, "channel-1"),
        hub.subscribe(CHANNEL_A, "channel-1"),
        hub.subscribe(CHANNEL_A, "channel-2"),
    ]

    with pytest.raises(StreamCapacityError):
        hub.subscribe(CHANNEL_A, "channel-1")
    with pytest.raises(StreamCapacityError):
        hub.subscribe(CHANNEL_A, "channel-3")

    for subscription in subscriptions:
        subscription.close()


@pytest.mark.asyncio
async def test_different_notify_channels_never_wake_each_other() -> None:
    """Two features sharing one hub must not cross-wake on the same channel_id."""
    hub = NotifyWakeHub(
        "postgresql://test:test@localhost/test",
        notify_channels=[CHANNEL_A, CHANNEL_B],
    )
    a_side = hub.subscribe(CHANNEL_A, "channel-1")
    b_side = hub.subscribe(CHANNEL_B, "channel-1")

    hub.notify(CHANNEL_A, "channel-1")

    await asyncio.wait_for(a_side.wait(), timeout=0.1)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(b_side.wait(), timeout=0.01)

    a_side.close()
    b_side.close()
    assert hub.subscriber_count == 0


@pytest.mark.asyncio
async def test_reconnect_wakes_every_subscriber_for_cursor_replay() -> None:
    hub = NotifyWakeHub(
        "postgresql://test:test@localhost/test",
        notify_channels=[CHANNEL_A, CHANNEL_B],
    )
    first = hub.subscribe(CHANNEL_A, "channel-1")
    second = hub.subscribe(CHANNEL_B, "channel-2")

    hub.notify_all()

    await asyncio.wait_for(first.wait(), timeout=0.1)
    await asyncio.wait_for(second.wait(), timeout=0.1)
    first.close()
    second.close()


@pytest.mark.asyncio
async def test_listener_adds_all_channels_and_reconnects_with_replay_wake(monkeypatch) -> None:
    drop_listener = asyncio.Event()

    async def fail_keepalive_after_first_wake(_query: str) -> None:
        await drop_listener.wait()
        raise ConnectionError("listener dropped")

    first_connection = AsyncMock()
    first_connection.execute.side_effect = fail_keepalive_after_first_wake
    second_connection = AsyncMock()
    connect = AsyncMock(side_effect=[first_connection, second_connection])
    monkeypatch.setattr(stream_module.asyncpg, "connect", connect)
    hub = NotifyWakeHub(
        "postgresql://test:test@localhost/test",
        notify_channels=[CHANNEL_A, CHANNEL_B],
        keepalive_seconds=0.01,
        reconnect_initial_seconds=0.01,
    )
    subscription = hub.subscribe(CHANNEL_A, "channel-1")

    hub.start()
    hub.start()
    try:
        await asyncio.wait_for(subscription.wait(), timeout=0.2)
        drop_listener.set()
        await asyncio.wait_for(subscription.wait(), timeout=1.0)

        assert connect.await_count == 2
        assert first_connection.add_listener.await_count == 2  # one per notify channel
        assert second_connection.add_listener.await_count == 2
    finally:
        await hub.stop()
        subscription.close()


def test_reconnect_backoff_defaults_to_five_second_cap() -> None:
    """Live Display's worst-case dead-air on listener drop must stay short for
    Video Queue overlays too — the previous 30s cap was fine for cosmetic
    check-in animations but is dead air on a stream. See
    docs/guides/cloudflare-pages.md."""
    hub = NotifyWakeHub(
        "postgresql://test:test@localhost/test",
        notify_channels=[CHANNEL_A],
    )
    assert hub._max_reconnect_seconds == 5.0


@pytest.mark.asyncio
async def test_reconnect_backoff_never_exceeds_configured_cap(monkeypatch) -> None:
    connect = AsyncMock(side_effect=ConnectionError("down"))
    monkeypatch.setattr(stream_module.asyncpg, "connect", connect)
    hub = NotifyWakeHub(
        "postgresql://test:test@localhost/test",
        notify_channels=[CHANNEL_A],
        reconnect_initial_seconds=0.01,
        max_reconnect_seconds=0.05,
    )

    hub.start()
    try:
        # A 30s-capped backoff would retry at most once in this window; a 0.05s
        # cap retries repeatedly — poll instead of a fixed sleep so this isn't
        # flaky under a loaded test run, but still fails fast if the cap regresses.
        for _ in range(100):
            if connect.await_count >= 3:
                break
            await asyncio.sleep(0.05)
        assert connect.await_count >= 3
    finally:
        await hub.stop()


@pytest.mark.asyncio
async def test_invalid_notification_does_not_wake_subscribers() -> None:
    hub = NotifyWakeHub(
        "postgresql://test:test@localhost/test",
        notify_channels=[CHANNEL_A],
    )
    subscription = hub.subscribe(CHANNEL_A, "channel-1")

    hub._on_notification(MagicMock(), 1, CHANNEL_A, "not-json")

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(subscription.wait(), timeout=0.01)
    subscription.close()
