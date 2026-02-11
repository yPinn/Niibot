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
from core.logging import setup_logging
from routers import (
    analytics_router,
    auth_router,
    bots_router,
    channels_router,
    commands_router,
    events_router,
    stats_router,
)

logger = logging.getLogger(__name__)

# Track server start time
_start_time: float = 0.0
_heartbeat_task: asyncio.Task | None = None
_db_connect_task: asyncio.Task | None = None


async def _heartbeat(interval: int = 300) -> None:
    """Periodic heartbeat — log uptime and DB status"""
    while True:
        await asyncio.sleep(interval)
        uptime = int(time.time() - _start_time)
        db_manager = get_database_manager()
        db_ok = db_manager is not None and db_manager._pool is not None
        logger.info(f"Heartbeat: uptime={uptime}s, db={db_ok}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle startup and shutdown"""
    global _start_time, _heartbeat_task, _db_connect_task
    _start_time = time.time()

    settings = get_settings()

    # Startup
    logger.info("Starting Niibot API server")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Frontend URL: {settings.frontend_url}")

    # Initialize database (background — don't block port binding)
    db_manager = init_database_manager(settings.database_url)

    async def _connect_db() -> None:
        try:
            await db_manager.connect()
            logger.info("Database connected")
        except Exception as e:
            logger.exception(f"Failed to connect to database: {e}")

    _db_connect_task = asyncio.create_task(_connect_db())

    # Start heartbeat keep-alive task
    if settings.enable_keep_alive:
        _heartbeat_task = asyncio.create_task(_heartbeat(settings.keep_alive_interval))
        logger.info(f"Heartbeat started (interval={settings.keep_alive_interval}s)")

    yield

    # Shutdown
    logger.info("Shutting down Niibot API server")
    if _db_connect_task and not _db_connect_task.done():
        _db_connect_task.cancel()
    if _heartbeat_task:
        _heartbeat_task.cancel()
    try:
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
    app.include_router(bots_router.router)

    # Root endpoint
    @app.get("/")
    async def root():
        """Root endpoint - minimal service info"""
        return {"service": "niibot-api", "status": "running"}

    # Health check endpoint for Docker/K8s
    @app.get("/health")
    async def health():
        """Health check endpoint for Docker/K8s"""
        db_manager = get_database_manager()
        ready = db_manager is not None and db_manager._pool is not None
        return {
            "status": "healthy" if ready else "starting",
            "ready": ready,
        }

    # Detailed status endpoint
    @app.get("/status")
    async def status():
        """Status endpoint for detailed service info"""
        db_manager = get_database_manager()
        db_connected = db_manager is not None and db_manager._pool is not None
        return {
            "service": "niibot-api",
            "version": "2.0.0",
            "uptime_seconds": int(time.time() - _start_time),
            "db_connected": db_connected,
            "environment": settings.environment,
        }

    # Ping endpoint
    @app.api_route("/ping", methods=["GET", "HEAD"], response_class=PlainTextResponse)
    async def ping():
        """Ping endpoint"""
        return "pong"

    logger.info("FastAPI application configured")

    return app
