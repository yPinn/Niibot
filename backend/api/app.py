"""FastAPI application factory"""

import asyncio
import logging
import os
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response

from core.config import get_settings
from core.database import get_database_manager, init_database_manager
from core.dependencies import close_discord_api, close_twitch_api
from core.logging import setup_logging
from routers import (
    analytics_router,
    auth_router,
    bots_router,
    channels_router,
    commands_router,
    donation_router,
    events_router,
    game_queue_router,
    message_triggers_router,
    payment_config_router,
    stats_router,
    timers_router,
    video_queue_router,
)
from routers.bots_router import close_bots_http_client

logger = logging.getLogger(__name__)

# Track server start time and build info
_start_time: float = 0.0
_started_at: str = ""
_pool_heartbeat_task: asyncio.Task | None = None
_db_retry_task: asyncio.Task | None = None
_APP_VERSION = os.getenv("APP_VERSION", "dev")
_GIT_COMMIT = os.getenv("GIT_COMMIT", "unknown")


async def _pool_heartbeat_loop() -> None:
    """Periodically ping the DB pool to detect and recover dead connections.

    On failure, backs off to avoid flooding logs and wasting connections.
    After 3 consecutive failures, destroys the dead pool and creates a fresh
    one via ``DatabaseManager.reconnect()``.
    """
    interval = 60
    fail_count = 0
    while True:
        await asyncio.sleep(interval)
        try:
            db_manager = get_database_manager()
            if db_manager._pool is None:
                raise RuntimeError("Pool is None")
            async with db_manager._pool.acquire(timeout=10.0) as conn:
                await conn.fetchval("SELECT 1")
            if fail_count > 0:
                logger.info(f"Pool heartbeat recovered after {fail_count} failures")
            fail_count = 0
            interval = 60
        except asyncio.CancelledError:
            break
        except Exception as e:
            fail_count += 1
            if fail_count <= 3:
                logger.warning(f"Pool heartbeat failed ({fail_count}): {type(e).__name__}: {e}")

            # After 3 consecutive failures the pool is likely dead — reconnect
            if fail_count == 3:
                logger.warning("Pool appears dead, attempting reconnect...")
                try:
                    await db_manager.reconnect()
                    logger.info("Pool reconnected successfully")
                    fail_count = 0
                    interval = 60
                    continue
                except Exception as re_err:
                    logger.error(f"Pool reconnect failed: {type(re_err).__name__}: {re_err}")
                    # Reset so the counter climbs back to 3 and triggers
                    # another reconnect attempt; use slow interval to avoid hammering.
                    fail_count = 0
                    interval = 120
                    continue

            # Backoff: 60s → 120s max
            interval = min(60 * (2 ** min(fail_count - 1, 1)), 120)


async def _db_retry_loop(db_manager) -> None:
    """Background loop to retry DB connection after startup timeout."""
    delay = 5
    max_delay = 60
    while True:
        await asyncio.sleep(delay)
        if db_manager._pool is not None:
            logger.info("DB retry loop: pool already connected, stopping")
            return
        try:
            await db_manager.connect()
            logger.info("Database connected (background retry)")
            return
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.warning(
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
    logger.info("Starting Niibot API server")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Frontend URL: {settings.frontend_url}")

    # Initialize and connect database — wait up to 30s before accepting requests.
    # This prevents the "pool is closed" race where requests arrive before
    # the pool is ready. If connection times out, spawn a background retry loop.
    db_manager = init_database_manager(settings.database_url)

    try:
        await asyncio.wait_for(db_manager.connect(), timeout=30)
        logger.info("Database connected")
    except TimeoutError:
        logger.warning("DB connection timed out during startup, retrying in background")
        _db_retry_task = asyncio.create_task(_db_retry_loop(db_manager))
    except Exception as e:
        logger.error(
            f"DB connection failed during startup: {type(e).__name__}: {e}, retrying in background"
        )
        _db_retry_task = asyncio.create_task(_db_retry_loop(db_manager))

    # Start pool heartbeat to detect and recover dead connections
    _pool_heartbeat_task = asyncio.create_task(_pool_heartbeat_loop())

    yield

    # Shutdown
    logger.info("Shutting down Niibot API server")
    if _db_retry_task:
        _db_retry_task.cancel()
    if _pool_heartbeat_task:
        _pool_heartbeat_task.cancel()
    try:
        await close_twitch_api()
        await close_discord_api()
        await close_bots_http_client()
        await db_manager.disconnect()
        logger.info("Database disconnected")
    except Exception as e:
        logger.exception(f"Error during shutdown: {e}")


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    settings = get_settings()

    # Setup logging first
    setup_logging(settings)

    # Create FastAPI app with lifespan
    app = FastAPI(
        title="Niibot API",
        description="API server for Niibot - Twitch/Discord bot management",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Security headers — applied to every response
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response

    # Register routers
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
    app.include_router(bots_router.router)

    # Root endpoint
    @app.get("/")
    async def root():
        """Root endpoint - minimal service info"""
        return {"service": "niibot-api", "status": "running"}

    # Liveness probe — always 200, no external dependency
    @app.get("/health")
    async def health():
        """Liveness check — no DB dependency"""
        return {
            "status": "healthy",
            "uptime_seconds": int(time.time() - _start_time),
        }

    # Detailed status endpoint (includes DB health)
    @app.get("/status")
    async def status():
        """Readiness / status endpoint — includes actual DB health check"""
        db_manager = get_database_manager()
        db_ok = False
        if db_manager is not None and db_manager._pool is not None:
            db_ok = await db_manager.check_health()
        return {
            "service": "niibot-api",
            "version": _APP_VERSION,
            "git_commit": _GIT_COMMIT,
            "started_at": _started_at,
            "uptime_seconds": int(time.time() - _start_time),
            "db_connected": db_ok,
            "environment": settings.environment,
        }

    # Ping endpoint
    @app.api_route("/ping", methods=["GET", "HEAD"], response_class=PlainTextResponse)
    async def ping():
        """Ping endpoint"""
        return "pong"

    logger.info("FastAPI application configured")

    return app
