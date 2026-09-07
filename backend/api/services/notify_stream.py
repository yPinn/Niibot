"""One PostgreSQL LISTEN connection fanned out to every registered notify
channel's SSE subscribers, shared by every feature that needs NOTIFY-woken
streaming (Live Display, Video Queue, ...).

A single wake-only listener connection is deliberate: each API process may
hold only one connection outside the pool for this purpose (see
docs/guides/cloudflare-pages.md). Adding a second feature must extend the
``notify_channels`` this hub listens on, never open a second hub.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

import asyncpg

from shared.database import resolve_db_ssl

LOGGER = logging.getLogger(__name__)


class StreamCapacityError(RuntimeError):
    """The process or (notify_channel, channel_id) pair already has the configured
    number of open streams."""


def encode_sse(event: str, data: Mapping[str, Any]) -> str:
    """Encode one named JSON SSE frame without permitting line injection."""
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'), default=str)}\n\n"


_SubscriberKey = tuple[str, str]  # (notify_channel, channel_id)


class WakeSubscription:
    def __init__(self, hub: NotifyWakeHub, key: _SubscriberKey, queue: asyncio.Queue[None]) -> None:
        self._hub = hub
        self._key = key
        self._queue = queue
        self._closed = False

    @property
    def channel_id(self) -> str:
        return self._key[1]

    async def wait(self) -> None:
        await self._queue.get()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._hub._unsubscribe(self._key, self._queue)


class NotifyWakeHub:
    """Reconnectable wake-only NOTIFY listener with bounded per-subscriber queues.

    Subscribers are keyed by ``(notify_channel, channel_id)`` so unrelated
    features sharing this hub never wake each other's streams.
    """

    def __init__(
        self,
        database_url: str,
        *,
        notify_channels: Sequence[str],
        queue_size: int = 1,
        keepalive_seconds: float = 30.0,
        reconnect_initial_seconds: float = 1.0,
        max_reconnect_seconds: float = 5.0,
        max_subscribers_per_channel: int = 10,
        max_subscribers: int = 1_000,
    ) -> None:
        self._database_url = database_url
        self._notify_channels = tuple(notify_channels)
        self._queue_size = queue_size
        self._keepalive_seconds = keepalive_seconds
        self._reconnect_initial_seconds = reconnect_initial_seconds
        self._max_reconnect_seconds = max_reconnect_seconds
        self._max_subscribers_per_channel = max_subscribers_per_channel
        self._max_subscribers = max_subscribers
        self._subscribers: dict[_SubscriberKey, set[asyncio.Queue[None]]] = defaultdict(set)
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    @property
    def subscriber_count(self) -> int:
        return sum(len(queues) for queues in self._subscribers.values())

    def subscribe(self, notify_channel: str, channel_id: str) -> WakeSubscription:
        key = (notify_channel, channel_id)
        if (
            self.subscriber_count >= self._max_subscribers
            or len(self._subscribers.get(key, ())) >= self._max_subscribers_per_channel
        ):
            raise StreamCapacityError("Stream capacity reached")
        queue: asyncio.Queue[None] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers[key].add(queue)
        return WakeSubscription(self, key, queue)

    def _unsubscribe(self, key: _SubscriberKey, queue: asyncio.Queue[None]) -> None:
        queues = self._subscribers.get(key)
        if queues is None:
            return
        queues.discard(queue)
        if not queues:
            self._subscribers.pop(key, None)

    @staticmethod
    def _wake(queue: asyncio.Queue[None]) -> None:
        if queue.full():
            return
        queue.put_nowait(None)

    def notify(self, notify_channel: str, channel_id: str) -> None:
        for queue in tuple(self._subscribers.get((notify_channel, channel_id), ())):
            self._wake(queue)

    def notify_all(self) -> None:
        for queues in tuple(self._subscribers.values()):
            for queue in tuple(queues):
                self._wake(queue)

    def _on_notification(
        self, connection: asyncpg.Connection, pid: int, channel: str, raw: str
    ) -> None:
        del connection, pid
        try:
            message = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            LOGGER.warning("notify_wake_hub_invalid_payload", extra={"notify_channel": channel})
            return
        channel_id = message.get("channel_id") if isinstance(message, dict) else None
        if isinstance(channel_id, str) and channel_id:
            self.notify(channel, channel_id)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping.clear()
            self._task = asyncio.create_task(self._run(), name="notify-wake-listener")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _run(self) -> None:
        delay = self._reconnect_initial_seconds
        while not self._stopping.is_set():
            connection: asyncpg.Connection | None = None
            try:
                kwargs: dict[str, object] = {"dsn": self._database_url}
                ssl_mode = resolve_db_ssl(self._database_url)
                if ssl_mode is not None:
                    kwargs["ssl"] = ssl_mode
                connection = await asyncpg.connect(**kwargs)
                for notify_channel in self._notify_channels:
                    await connection.add_listener(notify_channel, self._on_notification)
                LOGGER.info("notify_wake_hub_connected")
                self.notify_all()
                delay = self._reconnect_initial_seconds
                while not self._stopping.is_set():
                    try:
                        await asyncio.wait_for(
                            self._stopping.wait(), timeout=self._keepalive_seconds
                        )
                    except TimeoutError:
                        await connection.execute("SELECT 1")
            except asyncio.CancelledError:
                return
            except Exception:
                LOGGER.exception("notify_wake_hub_disconnected")
                try:
                    await asyncio.wait_for(self._stopping.wait(), timeout=delay)
                except TimeoutError:
                    delay = min(delay * 2, self._max_reconnect_seconds)
            finally:
                if connection is not None:
                    for notify_channel in self._notify_channels:
                        try:
                            await connection.remove_listener(notify_channel, self._on_notification)
                        except Exception:
                            LOGGER.debug("notify_wake_hub_remove_listener_failed", exc_info=True)
                    try:
                        await connection.close()
                    except Exception:
                        LOGGER.debug("notify_wake_hub_close_failed", exc_info=True)
