"""One PostgreSQL listener fanned out to all Live Display SSE clients in this process."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

import asyncpg

from shared.database import resolve_db_ssl

LOGGER = logging.getLogger(__name__)
NOTIFY_CHANNEL = "community_overlay_updates"


class OverlayCapacityError(RuntimeError):
    """The process or channel already has the configured number of open streams."""


def encode_sse(event: str, data: Mapping[str, Any]) -> str:
    """Encode one named JSON SSE frame without permitting line injection."""
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'), default=str)}\n\n"


class OverlaySubscription:
    def __init__(self, hub: OverlayUpdateHub, channel_id: str, queue: asyncio.Queue[None]) -> None:
        self._hub = hub
        self.channel_id = channel_id
        self._queue = queue
        self._closed = False

    async def wait(self) -> None:
        await self._queue.get()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._hub._unsubscribe(self.channel_id, self._queue)


class OverlayUpdateHub:
    """Reconnectable wake-only NOTIFY listener with bounded per-client queues."""

    def __init__(
        self,
        database_url: str,
        *,
        queue_size: int = 1,
        keepalive_seconds: float = 30.0,
        reconnect_initial_seconds: float = 1.0,
        max_subscribers_per_channel: int = 10,
        max_subscribers: int = 1_000,
    ) -> None:
        self._database_url = database_url
        self._queue_size = queue_size
        self._keepalive_seconds = keepalive_seconds
        self._reconnect_initial_seconds = reconnect_initial_seconds
        self._max_subscribers_per_channel = max_subscribers_per_channel
        self._max_subscribers = max_subscribers
        self._subscribers: dict[str, set[asyncio.Queue[None]]] = defaultdict(set)
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    @property
    def subscriber_count(self) -> int:
        return sum(len(queues) for queues in self._subscribers.values())

    def subscribe(self, channel_id: str) -> OverlaySubscription:
        if (
            self.subscriber_count >= self._max_subscribers
            or len(self._subscribers.get(channel_id, ())) >= self._max_subscribers_per_channel
        ):
            raise OverlayCapacityError("Live Display stream capacity reached")
        queue: asyncio.Queue[None] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers[channel_id].add(queue)
        return OverlaySubscription(self, channel_id, queue)

    def _unsubscribe(self, channel_id: str, queue: asyncio.Queue[None]) -> None:
        queues = self._subscribers.get(channel_id)
        if queues is None:
            return
        queues.discard(queue)
        if not queues:
            self._subscribers.pop(channel_id, None)

    @staticmethod
    def _wake(queue: asyncio.Queue[None]) -> None:
        if queue.full():
            return
        queue.put_nowait(None)

    def notify(self, channel_id: str) -> None:
        for queue in tuple(self._subscribers.get(channel_id, ())):
            self._wake(queue)

    def notify_all(self) -> None:
        for queues in tuple(self._subscribers.values()):
            for queue in tuple(queues):
                self._wake(queue)

    def _on_notification(
        self, connection: asyncpg.Connection, pid: int, channel: str, raw: str
    ) -> None:
        del connection, pid, channel
        try:
            message = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            LOGGER.warning("community_overlay_notify_invalid")
            return
        channel_id = message.get("channel_id") if isinstance(message, dict) else None
        if isinstance(channel_id, str) and channel_id:
            self.notify(channel_id)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping.clear()
            self._task = asyncio.create_task(self._run(), name="community-overlay-listener")

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
                await connection.add_listener(NOTIFY_CHANNEL, self._on_notification)
                LOGGER.info("community_overlay_listener_connected")
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
                LOGGER.exception("community_overlay_listener_disconnected")
                try:
                    await asyncio.wait_for(self._stopping.wait(), timeout=delay)
                except TimeoutError:
                    delay = min(delay * 2, 30.0)
            finally:
                if connection is not None:
                    try:
                        await connection.remove_listener(NOTIFY_CHANNEL, self._on_notification)
                        await connection.close()
                    except Exception:
                        LOGGER.debug("community_overlay_listener_close_failed", exc_info=True)
