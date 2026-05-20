"""FastAPI application factory"""

import asyncio
import logging
import os
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from core.config import get_settings
from core.database import get_database_manager, init_database_manager
from core.dependencies import close_twitch_api
from core.logging import setup_logging
from routers import (
    admin_router,
    ai_settings_router,
    analytics_router,
    auth_router,
    bots_router,
    channels_router,
    commands_router,
    crosshairs_router,
    discord_webhook_router,
    donation_router,
    events_router,
    game_queue_router,
    message_triggers_router,
    payment_config_router,
    releases_router,
    stats_router,
    timers_router,
    video_queue_router,
)
from routers.bots_router import close_bots_http_client
from shared.database import pool_heartbeat_loop

LOGGER: logging.Logger = logging.getLogger(__name__)

# Track server start time and build info
_start_time: float = 0.0
_started_at: str = ""
_pool_heartbeat_task: asyncio.Task | None = None
_db_retry_task: asyncio.Task | None = None
_APP_VERSION = os.getenv("APP_VERSION", "dev")
_GIT_COMMIT = os.getenv("GIT_COMMIT", "unknown")
_REQUEST_TIMEOUT = 30.0


async def _db_retry_loop(db_manager) -> None:
    """Background loop to retry DB connection after startup timeout."""
    delay = 5
    max_delay = 60
    while True:
        await asyncio.sleep(delay)
        if db_manager.is_connected:
            LOGGER.info("DB retry loop: pool already connected, stopping")
            return
        try:
            await db_manager.connect()
            LOGGER.info("Database connected (background retry)")
            return
        except asyncio.CancelledError:
            return
        except Exception as e:
            LOGGER.warning(
                f"DB background retry failed: {type(e).__name__}: {e}, next retry in {min(delay * 2, max_delay)}s"
            )
            delay = min(delay * 2, max_delay)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle startup and shutdown"""
    global _start_time, _started_at, _pool_heartbeat_task, _db_retry_task
    _start_time = time.time()
    _started_at = datetime.now(UTC).isoformat()

    settings = get_settings()

    # Startup
    LOGGER.info(
        "Starting Niibot API | env=%s frontend=%s bot_id=%s owner_id=%s",
        settings.environment,
        settings.frontend_url,
        settings.bot_id or "(not set)",
        settings.owner_id or "(not set)",
    )

    # Initialize and connect database — wait up to 30s before accepting requests.
    # This prevents the "pool is closed" race where requests arrive before
    # the pool is ready. If connection times out, spawn a background retry loop.
    db_manager = init_database_manager(settings.database_url)

    try:
        await asyncio.wait_for(db_manager.connect(), timeout=30)
        LOGGER.info("Database connected")
    except TimeoutError:
        LOGGER.error(
            "DB connection timed out during startup, all DB endpoints unavailable — retrying in background"
        )
        _db_retry_task = asyncio.create_task(_db_retry_loop(db_manager))
    except Exception as e:
        LOGGER.error(
            f"DB connection failed during startup: {type(e).__name__}: {e}, retrying in background"
        )
        _db_retry_task = asyncio.create_task(_db_retry_loop(db_manager))

    # Start pool heartbeat to detect and recover dead connections
    _pool_heartbeat_task = asyncio.create_task(pool_heartbeat_loop(db_manager))

    yield

    # Shutdown
    LOGGER.info("Shutting down Niibot API server")
    if _db_retry_task:
        _db_retry_task.cancel()
    if _pool_heartbeat_task:
        _pool_heartbeat_task.cancel()
    try:
        await close_twitch_api()
        await close_bots_http_client()
        await db_manager.disconnect()
        LOGGER.info("Database disconnected")
    except Exception:
        LOGGER.exception("Error during shutdown")


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    settings = get_settings()

    # Setup logging first
    setup_logging(settings)

    # Create FastAPI app with lifespan
    app = FastAPI(
        title="Niibot API",
        description="API server for Niibot - Twitch/Discord bot management",
        version=_APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
    )

    # Configure CORS — explicit list avoids exposing unnecessary methods/headers
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Cookie", "X-Request-ID"],
    )

    # ── Middleware stack (innermost registered first) ────────────────────

    # 1. Security headers (innermost — runs last on request, first on response)
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        response.headers["Content-Security-Policy"] = "default-src 'none'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response

    # 2. Request ID — accept upstream ID or generate; echoed in every response
    @app.middleware("http")
    async def add_request_id(request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # 3. Request timeout (outermost — wraps everything; returns 504 on breach)
    @app.middleware("http")
    async def request_timeout(request: Request, call_next) -> Response:
        try:
            return await asyncio.wait_for(call_next(request), timeout=_REQUEST_TIMEOUT)
        except TimeoutError:
            rid = getattr(request.state, "request_id", "-")
            LOGGER.warning("Request timed out [%s]: %s %s", rid, request.method, request.url.path)
            return JSONResponse(
                status_code=504,
                content={"detail": "Request timed out"},
                headers={"X-Request-ID": rid},
            )

    # ── Global exception handler ─────────────────────────────────────────
    # Catches any exception that escapes FastAPI's built-in HTTPException /
    # ValidationError handlers.  Logs with request ID so the 500 is traceable.
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        rid = getattr(request.state, "request_id", "-")
        LOGGER.exception("Unhandled exception [%s]: %s %s", rid, request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
            headers={"X-Request-ID": rid},
        )

    # Register routers
    app.include_router(discord_webhook_router.router)
    app.include_router(ai_settings_router.router)
    app.include_router(admin_router.router)
    app.include_router(auth_router.router)
    app.include_router(channels_router.router)
    app.include_router(analytics_router.router)
    app.include_router(stats_router.router)
    app.include_router(commands_router.router)
    app.include_router(events_router.router)
    app.include_router(game_queue_router.router)
    app.include_router(video_queue_router.router)
    app.include_router(timers_router.router)
    app.include_router(message_triggers_router.router)
    app.include_router(payment_config_router.router)
    app.include_router(donation_router.router)
    app.include_router(crosshairs_router.router)
    app.include_router(bots_router.router)
    app.include_router(releases_router.router)

    # Root endpoint
    @app.get("/")
    async def root():
        """Root endpoint - minimal service info"""
        return {"service": "niibot-api", "status": "running"}

    # Liveness probe — always 200, no external dependency
    @app.get("/health")
    async def health():
        """Liveness check — no DB dependency"""
        try:
            ready = get_database_manager().is_connected
        except RuntimeError:
            ready = False
        return {
            "status": "healthy",
            "ready": ready,
            "uptime_seconds": int(time.time() - _start_time),
        }

    # Detailed status endpoint (includes DB health)
    @app.get("/status")
    async def status():
        """Readiness / status endpoint — includes DB health and build metadata."""
        db_ok = False
        try:
            db_manager = get_database_manager()
            if db_manager.is_connected:
                db_ok = await db_manager.check_health()
        except RuntimeError:
            pass  # DB manager not yet initialized

        return {
            "service": "niibot-api",
            "version": _APP_VERSION,
            "git_commit": _GIT_COMMIT,
            "started_at": _started_at,
            "environment": settings.environment,
            "uptime_seconds": int(time.time() - _start_time),
            "db_connected": db_ok,
        }

    # Ping endpoint
    @app.api_route("/ping", methods=["GET", "HEAD"], response_class=PlainTextResponse)
    async def ping():
        """Ping endpoint"""
        return "pong"

    LOGGER.info("FastAPI application configured")

    return app
