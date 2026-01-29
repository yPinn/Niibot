"""HTTP health check server for Render deployment"""

import logging

from aiohttp import web

logger = logging.getLogger("discord_bot.http_server")


class HealthCheckServer:
    def __init__(self, bot, host="0.0.0.0", port=8080):
        self.bot = bot
        self.host = host
        self.port = port
        self.app = web.Application()
        self.runner = None
        self._setup_routes()

    def _setup_routes(self):
        self.app.router.add_get("/", self.handle_root)
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/ping", self.handle_ping)

    async def handle_root(self, request):
        return web.json_response({
            "service": "Niibot Discord Bot",
            "status": "running",
            "bot_ready": self.bot.is_ready(),
            "latency_ms": round(self.bot.latency * 1000, 2) if self.bot.is_ready() else None
        })

    async def handle_health(self, request):
        # 永遠回傳 200，確保 Render 不會在啟動期間判定失敗
        # 使用 ?deep=true 進行完整健康檢查
        deep = request.query.get("deep", "").lower() == "true"

        bot_ready = self.bot.is_ready()
        response = {
            "status": "healthy" if bot_ready else "starting",
            "bot_ready": bot_ready,
        }

        if bot_ready:
            response["latency_ms"] = round(self.bot.latency * 1000, 2)

        # 深度檢查時，未就緒才回傳 503
        status = 503 if deep and not bot_ready else 200
        return web.json_response(response, status=status)

    async def handle_ping(self, request):
        return web.Response(text="pong")

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        logger.info(f"HTTP server started on {self.host}:{self.port}")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
            logger.info("HTTP server stopped")
