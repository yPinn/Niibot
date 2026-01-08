"""FastAPI application factory"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from core.config import get_settings
from core.database import init_database_manager
from core.logging import setup_logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import analytics_router, auth_router, channels_router, commands, stats

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    FastAPI lifespan context manager for startup and shutdown events

    This handles:
    - Database connection pool initialization on startup
    - Database connection pool cleanup on shutdown
    """
    settings = get_settings()

    # Startup
    logger.info("Starting Niibot API server")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Frontend URL: {settings.frontend_url}")

    # Initialize database
    try:
        db_manager = init_database_manager(settings.database_url)
        await db_manager.connect()
        logger.info("Database connected")
    except Exception as e:
        logger.exception(f"Failed to connect to database: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down Niibot API server")
    try:
        await db_manager.disconnect()
        logger.info("Database disconnected")
    except Exception as e:
        logger.exception(f"Error during shutdown: {e}")


def create_app() -> FastAPI:
    """
    Application factory - creates and configures the FastAPI application

    Returns:
        Configured FastAPI application instance
    """
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
    app.include_router(stats.router)
    app.include_router(commands.router)

    # Health check endpoint
    @app.get("/api/health")
    async def health_check():
        """Health check endpoint"""
        return {
            "status": "ok",
            "service": "niibot-api",
            "version": "2.0.0",
            "environment": settings.environment,
        }

    # Root endpoint
    @app.get("/")
    async def root():
        """Root endpoint with API information"""
        return {
            "service": "Niibot API",
            "version": "2.0.0",
            "docs": "/docs" if settings.is_development else "disabled in production",
            "health": "/api/health",
        }

    logger.info("FastAPI application configured")

    return app
