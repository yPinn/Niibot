"""HTTP health check server"""

import asyncio
import logging
import os
import time
from typing import TYPE_CHECKING, Any

from aiohttp import web

if TYPE_CHECKING:
    from discord.ext.commands import Bot

logger = logging.getLogger("discord_bot.health_server")


class HealthCheckServer:
    """HTTP health check server"""

    def __init__(
        self, bot: "Bot | None" = None, host: str = "0.0.0.0", port: int | None = None
    ) -> None:
        self.bot: Any = bot
        self.host = host
        self.port = port or int(os.getenv("PORT", "8080"))
        self.app = web.Application()
        self.runner: web.AppRunner | None = None
        self._start_time: float = time.time()
        self._heartbeat_task: asyncio.Task | None = None
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Configure HTTP routes"""
        self.app.router.add_get("/", self.handle_root)
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/status", self.handle_status)
        self.app.router.add_get("/ping", self.handle_ping)

    async def handle_root(self, request: web.Request) -> web.Response:
        """Root endpoint - minimal service info"""
        return web.json_response({"service": "niibot-discord", "status": "running"})

    async def handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint for Render/Docker — always 200 (liveness)"""
        ready = self.bot is not None and self.bot.is_ready()
        return web.json_response(
            {"status": "healthy" if ready else "starting", "ready": ready},
        )

    async def handle_status(self, request: web.Request) -> web.Response:
        """Status endpoint for API server integration"""
        bot_ready = self.bot is not None and self.bot.is_ready()
        return web.json_response(
            {
                "service": "niibot-discord",
                "bot_id": str(self.bot.user.id) if bot_ready and self.bot.user else None,
                "uptime_seconds": int(time.time() - self._start_time),
                "connected_channels": len(self.bot.guilds) if bot_ready else 0,
            }
        )

    async def handle_ping(self, request: web.Request) -> web.Response:
        """Ping endpoint"""
        return web.Response(text="pong")

    async def _heartbeat(self) -> None:
        """Periodic heartbeat — log uptime and bot status"""
        while True:
            await asyncio.sleep(300)
            uptime = int(time.time() - self._start_time)
            ready = self.bot.is_ready() if self.bot else False
            guilds = len(self.bot.guilds) if ready else 0
            logger.info(f"Heartbeat: uptime={uptime}s, ready={ready}, guilds={guilds}")

    async def start(self) -> None:
        """Start health check server"""
        try:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            site = web.TCPSite(self.runner, self.host, self.port)
            await site.start()

            self._heartbeat_task = asyncio.create_task(self._heartbeat())

            logger.info(f"Health server started on {self.host}:{self.port}")
            logger.info(f"  GET http://{self.host}:{self.port}/health - Health check")
            logger.info(f"  GET http://{self.host}:{self.port}/status - Detailed status")
        except Exception as e:
            logger.exception(f"Failed to start health server: {e}")
            raise

    async def stop(self) -> None:
        """Stop health check server"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self.runner:
            try:
                await self.runner.cleanup()
                logger.info("Health server stopped")
            except Exception as e:
                logger.exception(f"Error stopping health server: {e}")
