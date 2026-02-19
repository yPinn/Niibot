"""FastAPI application factory"""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

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
    events_router,
    game_queue_router,
    stats_router,
)

logger = logging.getLogger(__name__)

# Track server start time
_start_time: float = 0.0
_heartbeat_task: asyncio.Task | None = None
_pool_heartbeat_task: asyncio.Task | None = None
_db_retry_task: asyncio.Task | None = None


async def _heartbeat(interval: int = 300) -> None:
    """Periodic heartbeat — log uptime and DB status"""
    while True:
        await asyncio.sleep(interval)
        uptime = int(time.time() - _start_time)
        db_manager = get_database_manager()
        db_ok = db_manager is not None and await db_manager.check_health()
        logger.info(f"Heartbeat: uptime={uptime}s, db={db_ok}")


async def _pool_heartbeat_loop() -> None:
    """Periodically ping the DB pool to keep idle connections alive.

    Constraint chain: heartbeat(15s) < max_inactive(45s) < Supavisor(~30-60s).
    On failure, backs off to avoid flooding logs and wasting connections.
    """
    interval = 15
    fail_count = 0
    while True:
        await asyncio.sleep(interval)
        try:
            db_manager = get_database_manager()
            if db_manager._pool is not None:
                async with db_manager._pool.acquire(timeout=30.0) as conn:
                    await conn.fetchval("SELECT 1")
                if fail_count > 0:
                    logger.info(f"Pool heartbeat recovered after {fail_count} failures")
                fail_count = 0
                interval = 15
        except asyncio.CancelledError:
            break
        except Exception as e:
            fail_count += 1
            if fail_count <= 3:
                logger.warning(f"Pool heartbeat failed ({fail_count}): {type(e).__name__}: {e}")
            elif fail_count == 4:
                logger.warning(
                    f"Pool heartbeat still failing ({fail_count}x), suppressing until recovery"
                )
            # Backoff: 15s → 30s → 60s → 120s max
            interval = min(15 * (2 ** min(fail_count - 1, 3)), 120)


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
    global _start_time, _heartbeat_task, _pool_heartbeat_task, _db_retry_task
    _start_time = time.time()

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

    # Start heartbeat keep-alive task
    if settings.enable_keep_alive:
        _heartbeat_task = asyncio.create_task(_heartbeat(settings.keep_alive_interval))
        logger.info(f"Heartbeat started (interval={settings.keep_alive_interval}s)")

    # Start pool heartbeat to prevent Supavisor idle kills
    _pool_heartbeat_task = asyncio.create_task(_pool_heartbeat_loop())

    yield

    # Shutdown
    logger.info("Shutting down Niibot API server")
    if _db_retry_task:
        _db_retry_task.cancel()
    if _pool_heartbeat_task:
        _pool_heartbeat_task.cancel()
    if _heartbeat_task:
        _heartbeat_task.cancel()
    try:
        await close_twitch_api()
        await close_discord_api()
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

    # Register routers
    app.include_router(auth_router.router)
    app.include_router(channels_router.router)
    app.include_router(analytics_router.router)
    app.include_router(stats_router.router)
    app.include_router(commands_router.router)
    app.include_router(events_router.router)
    app.include_router(game_queue_router.router)
    app.include_router(bots_router.router)

    # Root endpoint
    @app.get("/")
    async def root():
        """Root endpoint - minimal service info"""
        return {"service": "niibot-api", "status": "running"}

    # Liveness probe — always 200, no external dependency
    @app.get("/health")
    async def health():
        """Liveness check for Render / Docker / K8s (no DB dependency)"""
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
            "version": "2.0.0",
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
