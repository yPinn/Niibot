"""
HTTP 服務器用於 Render Web Service 部署
提供健康檢查端點，防止服務休眠
"""

import logging
from aiohttp import web

logger = logging.getLogger("discord_bot.http_server")


class HealthCheckServer:
    """簡單的 HTTP 健康檢查服務器"""

    def __init__(self, bot, host="0.0.0.0", port=8080):
        self.bot = bot
        self.host = host
        self.port = port
        self.app = web.Application()
        self.runner = None
        self._setup_routes()

    def _setup_routes(self):
        """設置路由"""
        self.app.router.add_get("/", self.handle_root)
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/ping", self.handle_ping)

    async def handle_root(self, request):
        """根路徑處理"""
        return web.json_response({
            "service": "Niibot Discord Bot",
            "status": "running",
            "bot_ready": self.bot.is_ready(),
            "latency_ms": round(self.bot.latency * 1000, 2) if self.bot.is_ready() else None
        })

    async def handle_health(self, request):
        """健康檢查端點"""
        if self.bot.is_ready():
            return web.json_response({
                "status": "healthy",
                "bot_ready": True,
                "latency_ms": round(self.bot.latency * 1000, 2)
            })
        else:
            return web.json_response({
                "status": "starting",
                "bot_ready": False
            }, status=503)

    async def handle_ping(self, request):
        """簡單的 ping 端點"""
        return web.Response(text="pong")

    async def start(self):
        """啟動 HTTP 服務器"""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        logger.info(f"HTTP server started on {self.host}:{self.port}")

    async def stop(self):
        """停止 HTTP 服務器"""
        if self.runner:
            await self.runner.cleanup()
            logger.info("HTTP server stopped")
