"""Base HTTP health check server for Discord and Twitch bot services."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from aiohttp import web

_APP_VERSION = os.getenv("APP_VERSION", "dev")
_GIT_COMMIT = os.getenv("GIT_COMMIT", "unknown")

LOGGER: logging.Logger = logging.getLogger(__name__)


class BaseHealthServer(ABC):
    """Shared HTTP health check server with standard routes.

    Subclasses must implement:
      - ``SERVICE_NAME`` — e.g. ``"nb-discord"``
      - ``get_ready()`` — whether the bot/service is fully operational
      - ``get_metrics()`` — service-specific fields for the ``/status`` response
    """

    SERVICE_NAME: str = "niibot"

    def __init__(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        self.host = host
        self.port = port
        self.app = web.Application()
        self.runner: web.AppRunner | None = None
        self._start_time: float = time.time()
        self._started_at: str = datetime.now(UTC).isoformat()
        self._heartbeat_task: asyncio.Task | None = None
        self._setup_routes()

    def _setup_routes(self) -> None:
        self.app.router.add_get("/", self.handle_root)
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/status", self.handle_status)
        self.app.router.add_get("/ping", self.handle_ping)

    @abstractmethod
    async def get_ready(self) -> bool:
        """Return True when the service is fully operational."""

    @abstractmethod
    async def get_metrics(self) -> dict:
        """Return service-specific fields to include in /status."""

    # ── Standard route handlers ──────────────────────────────────────────

    async def handle_root(self, request: web.Request) -> web.Response:
        return web.json_response({"service": self.SERVICE_NAME, "status": "running"})

    async def handle_health(self, request: web.Request) -> web.Response:
        """Liveness probe — always 200."""
        ready = await self.get_ready()
        return web.json_response(
            {
                "status": "healthy" if ready else "starting",
                "ready": ready,
                "uptime_seconds": int(time.time() - self._start_time),
            }
        )

    async def handle_status(self, request: web.Request) -> web.Response:
        """Readiness / detailed status endpoint."""
        ready = await self.get_ready()
        metrics = await self.get_metrics()
        data = {
            "service": self.SERVICE_NAME,
            "version": _APP_VERSION,
            "git_commit": _GIT_COMMIT,
            "started_at": self._started_at,
            "uptime_seconds": int(time.time() - self._start_time),
            "ready": ready,
            **metrics,
        }
        return web.json_response(data)

    async def handle_ping(self, request: web.Request) -> web.Response:
        return web.Response(text="pong")

    # ── Heartbeat ────────────────────────────────────────────────────────

    async def _heartbeat_loop(self) -> None:
        """Log uptime/status + memory gauges every 5 minutes.

        INFO (not DEBUG) so this survives production log filtering — it's
        the only periodic signal of memory trends for services that don't
        run their own dedicated gauge-log loop.
        """
        while True:
            await asyncio.sleep(300)
            uptime = int(time.time() - self._start_time)
            ready = await self.get_ready()
            metrics = await self.get_metrics()
            LOGGER.info(
                "runtime_gauges",
                extra={
                    "code": "RUNTIME.GAUGES",
                    "uptime_seconds": uptime,
                    "ready": ready,
                    **metrics,
                },
            )

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the health check HTTP server."""
        try:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            site = web.TCPSite(self.runner, self.host, self.port)
            await site.start()
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            LOGGER.info("Health server started on %s:%d", self.host, self.port)
        except Exception:
            LOGGER.exception("Failed to start health server")
            raise

    async def stop(self) -> None:
        """Stop the health check HTTP server."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        if self.runner:
            try:
                await self.runner.cleanup()
                LOGGER.info("Health server stopped")
            except Exception:
                LOGGER.exception("Error stopping health server")
