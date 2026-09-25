"""Bounded exclusive admission for Scrapling's single browser session."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class BrowserBusyError(RuntimeError):
    """Raised when the single browser already has its bounded queue filled."""


class BrowserAdmission:
    def __init__(self, *, max_queue_depth: int = 1, max_wait_seconds: float = 25.0) -> None:
        if max_queue_depth < 0:
            raise ValueError("max_queue_depth must not be negative")
        if max_wait_seconds <= 0:
            raise ValueError("max_wait_seconds must be positive")
        self._max_queue_depth = max_queue_depth
        self._max_wait_seconds = max_wait_seconds
        self._slot: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        self._slot.put_nowait(None)
        self._waiters = 0

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[None]:
        acquired = False
        try:
            self._slot.get_nowait()
            acquired = True
        except asyncio.QueueEmpty:
            if self._waiters >= self._max_queue_depth:
                raise BrowserBusyError("browser queue is full") from None
            self._waiters += 1
            try:
                await asyncio.wait_for(self._slot.get(), timeout=self._max_wait_seconds)
                acquired = True
            except TimeoutError as exc:
                raise BrowserBusyError("browser queue wait timed out") from exc
            finally:
                self._waiters -= 1
        try:
            yield
        finally:
            if acquired:
                self._slot.put_nowait(None)
