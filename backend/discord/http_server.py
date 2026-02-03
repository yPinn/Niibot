"""HTTP health check server for Render deployment"""

import logging
import time
from typing import Any

from aiohttp import web

logger = logging.getLogger("discord_bot.http_server")


class HealthCheckServer:
    def __init__(self, bot: Any, host: str = "0.0.0.0", port: int = 8080) -> None:
        self.bot = bot
        self.host = host
        self.port = port
        self.app = web.Application()
        self.runner: web.AppRunner | None = None
        self._start_time: float = time.time()
        self._setup_routes()

    def _setup_routes(self) -> None:
        self.app.router.add_get("/", self.handle_root)
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/ping", self.handle_ping)
        self.app.router.add_get("/status", self.handle_status)

    async def handle_root(self, request: web.Request) -> web.StreamResponse:
        """Root endpoint - minimal service info"""
        return web.json_response({"service": "niibot-discord", "status": "running"})

    async def handle_health(self, request: web.Request) -> web.StreamResponse:
        """Health check endpoint for Render/Docker — always 200 (liveness)"""
        ready = self.bot.is_ready()
        return web.json_response(
            {"status": "healthy" if ready else "starting", "ready": ready},
        )

    async def handle_ping(self, request: web.Request) -> web.StreamResponse:
        return web.Response(text="pong")

    async def handle_status(self, request: web.Request) -> web.StreamResponse:
        """Status endpoint for API server integration"""
        return web.json_response(
            {
                "service": "niibot-discord",
                "bot_id": str(self.bot.user.id) if self.bot.user else None,
                "uptime_seconds": int(time.time() - self._start_time),
                "connected_channels": len(self.bot.guilds) if self.bot.is_ready() else 0,
            }
        )

    async def start(self) -> None:
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        logger.info(f"HTTP server started on {self.host}:{self.port}")

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()
            logger.info("HTTP server stopped")
