"""FastAPI application factory"""

import asyncio
import logging
import os
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.config import get_settings
from core.database import get_database_manager, init_database_manager
from core.dependencies import close_twitch_api, require_activated
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
    matcher_router,
    message_triggers_router,
    payment_config_router,
    releases_router,
    stats_router,
    timers_router,
    video_queue_router,
)
from routers.bots_router import close_bots_http_client
from shared.database import pool_heartbeat_loop
from shared.errors import AppError, build_envelope

LOGGER: logging.Logger = logging.getLogger(__name__)

# Track server start time and build info
_start_time: float = 0.0
_started_at: str = ""
_pool_heartbeat_task: asyncio.Task | None = None
_db_retry_task: asyncio.Task | None = None
_APP_VERSION = os.getenv("APP_VERSION", "dev")
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

    # ── Middleware & error handling ─────────────────────────────────────
    #
    # FastAPI prepends middleware, so the LAST one registered is the
    # OUTERMOST. Target order, outer → inner:
    #
    #   CORS → request context → catch-all 500 → timeout → security headers
    #
    # CORS must be outermost so that error responses (500 / 504) still carry
    # Access-Control-Allow-Origin. Otherwise a cross-origin frontend sees a
    # bare network error and cannot read the body or the X-Request-ID header
    # it needs to report the failure.

    def _log_request_failure(
        request: Request,
        *,
        code: str,
        status: int,
        exc: BaseException | None = None,
        level: int = logging.ERROR,
        context: dict | None = None,
    ) -> None:
        LOGGER.log(
            level,
            "request_failed",
            extra={
                "code": code,
                "http_status": status,
                "http_method": request.method,
                "http_path": request.url.path,
                **(context or {}),
            },
            exc_info=exc if (exc is not None and level >= logging.ERROR) else None,
        )

    # innermost — security headers
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

    # request timeout → 504
    @app.middleware("http")
    async def request_timeout(request: Request, call_next) -> Response:
        try:
            return await asyncio.wait_for(call_next(request), timeout=_REQUEST_TIMEOUT)
        except TimeoutError:
            rid = getattr(request.state, "request_id", None)
            _log_request_failure(request, code="HTTP.504", status=504, level=logging.WARNING)
            return JSONResponse(
                status_code=504,
                content=build_envelope(
                    code="HTTP.504",
                    message="伺服器處理時間過長，請稍後再試",
                    request_id=rid,
                ),
            )

    # catch-all — anything with no registered handler. Runs *inside* CORS so
    # the 500 response is CORS-decorated (unlike Starlette's built-in 500).
    @app.middleware("http")
    async def catch_unhandled(request: Request, call_next) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:  # noqa: BLE001 — deliberate boundary
            rid = getattr(request.state, "request_id", None)
            _log_request_failure(request, code="INTERNAL.UNEXPECTED", status=500, exc=exc)
            return JSONResponse(
                status_code=500,
                content=build_envelope(
                    code="INTERNAL.UNEXPECTED",
                    message="系統暫時出了點狀況，請稍後再試",
                    request_id=rid,
                ),
            )

    # request context — accept upstream ID or generate; echoed on every
    # response, including the 500 / 504 built above.
    @app.middleware("http")
    async def add_request_context(request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # outermost — CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Cookie", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    # ── Exception handlers ──────────────────────────────────────────────
    # These run in Starlette's ExceptionMiddleware (inside every HTTP
    # middleware), so their responses pass back out through CORS normally.
    # All of them emit the same envelope shape as build_envelope().

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        _log_request_failure(
            request,
            code=exc.code,
            status=exc.http_status,
            exc=exc,
            level=exc.log_level,
            context=exc.context,
        )
        return JSONResponse(status_code=exc.http_status, content=exc.to_envelope(rid))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        _log_request_failure(
            request,
            code="VALIDATION.INVALID_INPUT",
            status=422,
            level=logging.INFO,
            context={"validation_errors": exc.errors()},
        )
        return JSONResponse(
            status_code=422,
            content=build_envelope(
                code="VALIDATION.INVALID_INPUT",
                message="輸入的內容有誤，請檢查後再試",
                request_id=rid,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        detail = exc.detail if isinstance(exc.detail, str) and exc.detail else "請求無法處理"
        if exc.status_code >= 500:
            _log_request_failure(
                request, code=f"HTTP.{exc.status_code}", status=exc.status_code, exc=exc
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=build_envelope(code=f"HTTP.{exc.status_code}", message=detail, request_id=rid),
            headers=exc.headers,
        )

    # Fallback for exceptions raised *outside* catch_unhandled (e.g. within
    # CORS itself). Rare; this response is not CORS-decorated.
    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        _log_request_failure(request, code="INTERNAL.UNEXPECTED", status=500, exc=exc)
        return JSONResponse(
            status_code=500,
            content=build_envelope(
                code="INTERNAL.UNEXPECTED",
                message="系統暫時出了點狀況，請稍後再試",
                request_id=rid,
            ),
        )

    _activated = [Depends(require_activated)]

    # Register routers
    # Public / webhook routers — no activation gate
    app.include_router(discord_webhook_router.router)
    app.include_router(auth_router.router)
    app.include_router(donation_router.router)
    # Admin router — gated by stricter require_owner inside the router itself
    app.include_router(admin_router.router)
    # Fully-private routers — every endpoint requires an activated account
    app.include_router(channels_router.router, dependencies=_activated)
    app.include_router(analytics_router.router, dependencies=_activated)
    app.include_router(matcher_router.router, dependencies=_activated)
    app.include_router(stats_router.router, dependencies=_activated)
    app.include_router(events_router.router, dependencies=_activated)
    app.include_router(timers_router.router, dependencies=_activated)
    app.include_router(message_triggers_router.router, dependencies=_activated)
    app.include_router(payment_config_router.router, dependencies=_activated)
    app.include_router(ai_settings_router.router, dependencies=_activated)
    app.include_router(bots_router.router, dependencies=_activated)
    app.include_router(releases_router.router, dependencies=_activated)
    # Mixed routers — public overlay endpoints exempt; activation enforced per-endpoint inside
    app.include_router(commands_router.router)
    app.include_router(game_queue_router.router)
    app.include_router(video_queue_router.router)
    app.include_router(crosshairs_router.router)

    # Root endpoint
    @app.get("/")
    async def root():
        """Root endpoint - minimal service info"""
        return {"service": "nb-api", "status": "running"}

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
            "service": "nb-api",
            "version": _APP_VERSION,
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
