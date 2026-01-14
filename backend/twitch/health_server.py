"""HTTP health check server"""

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from main import Bot

logger = logging.getLogger("Bot.Health")


class HealthCheckServer:
    """HTTP health check server"""

    def __init__(self, bot: "Bot", host: str = "0.0.0.0", port: int = 4344):
        self.bot = bot
        self.host = host
        self.port = port
        self.app = web.Application()
        self.runner: web.AppRunner | None = None
        self.start_time = datetime.utcnow()
        self._setup_routes()

    def _setup_routes(self):
        """Configure HTTP routes"""
        self.app.router.add_get("/", self.handle_root)
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/status", self.handle_status)
        self.app.router.add_get("/ping", self.handle_ping)

    async def handle_root(self, request: web.Request) -> web.Response:
        """Root endpoint with service info"""
        uptime = (datetime.utcnow() - self.start_time).total_seconds()
        return web.json_response(
            {
                "service": "Niibot Twitch Bot",
                "status": "running",
                "bot_id": self.bot.bot_id,
                "uptime_seconds": int(uptime),
                "connected_channels": len(self.bot._subscribed_channels),
            }
        )

    async def handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint for Docker/K8s"""
        try:
            is_ready = self.bot.bot_id is not None
            if is_ready:
                return web.json_response(
                    {
                        "status": "healthy",
                        "bot_ready": True,
                        "bot_id": self.bot.bot_id,
                    }
                )
            else:
                return web.json_response(
                    {"status": "starting", "bot_ready": False}, status=503
                )

        except Exception as e:
            logger.exception(f"Health check error: {e}")
            return web.json_response(
                {"status": "unhealthy", "error": str(e)}, status=503
            )

    async def handle_status(self, request: web.Request) -> web.Response:
        """Detailed status endpoint"""
        try:
            uptime = (datetime.utcnow() - self.start_time).total_seconds()

            return web.json_response(
                {
                    "status": "online",
                    "service": "niibot-twitch-bot",
                    "bot_id": self.bot.bot_id,
                    "uptime_seconds": int(uptime),
                    "connected_channels": len(self.bot._subscribed_channels),
                    "subscription_count": sum(
                        len(subs) for subs in self.bot._subscription_ids.values()
                    ),
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

        except Exception as e:
            logger.exception(f"Status check error: {e}")
            return web.json_response(
                {"status": "error", "error": str(e)}, status=500
            )

    async def handle_ping(self, request: web.Request) -> web.Response:
        """Ping endpoint"""
        return web.Response(text="pong")

    async def start(self) -> None:
        """Start health check server"""
        try:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            site = web.TCPSite(self.runner, self.host, self.port)
            await site.start()

            logger.info(f"HTTP health server started on {self.host}:{self.port}")
            logger.info(f"  GET http://{self.host}:{self.port}/health - Health check")
            logger.info(
                f"  GET http://{self.host}:{self.port}/status - Detailed status"
            )

        except Exception as e:
            logger.exception(f"Failed to start health server: {e}")
            raise

    async def stop(self) -> None:
        """Stop health check server"""
        if self.runner:
            try:
                await self.runner.cleanup()
                logger.info("HTTP health server stopped")
            except Exception as e:
                logger.exception(f"Error stopping health server: {e}")
