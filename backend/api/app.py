"""FastAPI application factory"""

import asyncio
import json
import logging
import os
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from core.config import get_settings
from core.database import get_database_manager, init_database_manager
from core.dependencies import (
    close_twitch_api,
    get_notify_hub,
    get_twitch_api,
    require_activated,
)
from core.error_handlers import log_request_failure, register_exception_handlers
from core.logging_setup import setup_logging
from routers import (
    admin_router,
    ai_settings_router,
    analytics_router,
    auth_router,
    bot_accounts_router,
    bots_router,
    channels_router,
    checkin_router,
    client_errors_router,
    command_import_router,
    commands_router,
    community_overlay_router,
    crosshairs_router,
    discord_webhook_router,
    donation_router,
    events_router,
    game_queue_router,
    matcher_router,
    message_triggers_router,
    payment_config_router,
    releases_router,
    roleplay_router,
    stats_router,
    tenants_router,
    timers_router,
    video_queue_router,
    vip_router,
)
from routers.bots_router import close_bots_http_client
from routers.checkin_router import close_checkin_import_http_client
from routers.client_errors_router import client_error_retention_loop
from routers.command_import_router import close_command_import_http_client
from routers.video_queue_router import video_queue_history_retention_loop
from services.assistant_scope_notifications import handle_assistant_scope_changed_notify
from services.twitch_authorization_service import TwitchAuthorizationService
from shared.assistant import ASSISTANT_SCOPE_CHANGED_CHANNEL
from shared.cache_invalidation import (
    clear_config_caches,
    invalidate_channel_caches,
    invalidate_channel_config,
    invalidate_module_config,
)
from shared.database import pool_heartbeat_loop
from shared.errors import build_envelope
from shared.gauges import collect_runtime_gauges
from shared.log_context import bind_log_context, clear_log_context
from shared.pg_listener import pg_listen
from shared.repositories.activation_code import activation_grant_cleanup_loop
from shared.repositories.community_overlay import community_overlay_cleanup_loop

LOGGER: logging.Logger = logging.getLogger(__name__)

# Track server start time and build info
_start_time: float = 0.0
_started_at: str = ""
_pool_heartbeat_task: asyncio.Task | None = None
_db_retry_task: asyncio.Task | None = None
_client_error_retention_task: asyncio.Task | None = None
_activation_cleanup_task: asyncio.Task | None = None
_community_overlay_cleanup_task: asyncio.Task | None = None
_video_queue_history_task: asyncio.Task | None = None
_config_change_listener_task: asyncio.Task | None = None
_assistant_scope_listener_task: asyncio.Task | None = None
_channel_toggle_listener_task: asyncio.Task | None = None
_cache_clear_task: asyncio.Task | None = None
_gauge_log_task: asyncio.Task | None = None
_twitch_authorization_task: asyncio.Task | None = None
_APP_VERSION = os.getenv("APP_VERSION", "dev")
_GIT_COMMIT = os.getenv("GIT_COMMIT", "unknown")
_REQUEST_TIMEOUT = 30.0
_CACHE_CLEAR_INTERVAL = 600.0  # 10 min safety net for pg_notify misses (see cache_invalidation.py)
_GAUGE_LOG_INTERVAL = 300.0  # 5 min, matches the twitch bot's heartbeat cadence
_TWITCH_AUTHORIZATION_INTERVAL = 900.0


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


async def _handle_config_change_notify(connection, pid, channel, payload) -> None:
    """Invalidate in-process config caches on `config_change` NOTIFY.

    Mirrors the twitch bot's own listener (`twitch/core/_notify_mixin.py`) so
    both processes' caches stay in sync with DB writes made by either one —
    without this, an API-side cache (TTL up to 3600s) could serve stale data
    for up to an hour after a change made by the bot or another API replica.
    """
    try:
        data = json.loads(payload)
        table = data.get("table", "")
        if table == "module_config":
            invalidate_module_config()
            LOGGER.info("config_change_invalidated", extra={"table": table})
            return
        channel_id = data.get("channel_id")
        if not channel_id:
            return
        invalidate_channel_config(channel_id)
        LOGGER.info(
            "config_change_invalidated",
            extra={"channel_id": channel_id, "table": table},
        )
    except Exception as e:
        LOGGER.warning(f"Error handling config_change notify: {e}")


async def _handle_channel_toggle_notify(connection, pid, channel, payload) -> None:
    """Invalidate `_channel_cache`/`_enabled_channels_cache` on `channel_toggle` NOTIFY."""
    try:
        data = json.loads(payload)
        channel_id = data.get("channel_id")
        if not channel_id:
            return
        invalidate_channel_caches(channel_id)
        LOGGER.info("channel_toggle_invalidated", extra={"channel_id": channel_id})
    except Exception as e:
        LOGGER.warning(f"Error handling channel_toggle notify: {e}")


async def _cache_clear_loop() -> None:
    """Periodic full-clear safety net for config caches (see cache_invalidation.py)."""
    while True:
        try:
            await asyncio.sleep(_CACHE_CLEAR_INTERVAL)
            clear_config_caches()
            LOGGER.debug("Periodic cache clear complete")
        except asyncio.CancelledError:
            break
        except Exception as e:
            LOGGER.warning(f"Periodic cache clear error: {e}")


async def _gauge_log_loop(db_manager) -> None:
    """Log DB pool + cache size gauges periodically so memory trends are
    visible without polling `/status`."""
    while True:
        try:
            await asyncio.sleep(_GAUGE_LOG_INTERVAL)
            LOGGER.info(
                "runtime_gauges",
                extra={"code": "RUNTIME.GAUGES", **collect_runtime_gauges(db_manager)},
            )
        except asyncio.CancelledError:
            break
        except Exception as e:
            LOGGER.warning(f"Gauge log error: {e}")


async def _twitch_authorization_loop(db_manager, settings) -> None:
    """Validate every stored Twitch credential at least hourly in bounded batches."""
    while True:
        try:
            delay = _TWITCH_AUTHORIZATION_INTERVAL
            if db_manager.is_connected:
                service = TwitchAuthorizationService(
                    db_manager.pool,
                    twitch_api=get_twitch_api(),
                    token_encryption_key=settings.twitch_token_encryption_key,
                    client_id=settings.client_id,
                )
                checked = await service.check_due_credentials(limit=25)
                if checked:
                    LOGGER.info(
                        "Twitch authorization reconciliation checked %d credential(s)", checked
                    )
                if checked == 25:
                    # Drain large installations in bounded bursts without
                    # waiting another 15 minutes between pages.
                    delay = 5.0
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            break
        except Exception:
            LOGGER.exception("Twitch authorization reconciliation failed")
            await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle startup and shutdown"""
    global _start_time, _started_at, _pool_heartbeat_task, _db_retry_task
    global _client_error_retention_task, _activation_cleanup_task, _community_overlay_cleanup_task
    global _video_queue_history_task
    global _config_change_listener_task, _assistant_scope_listener_task
    global _channel_toggle_listener_task
    global _cache_clear_task, _gauge_log_task
    global _twitch_authorization_task
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

    # Daily prune of the client_errors telemetry table
    _client_error_retention_task = asyncio.create_task(client_error_retention_loop(db_manager))

    # Daily expiry + scrub of stale activation grants
    _activation_cleanup_task = asyncio.create_task(activation_grant_cleanup_loop(db_manager))

    # Daily prune of expired visual events; check-in ledgers remain permanent.
    _community_overlay_cleanup_task = asyncio.create_task(
        community_overlay_cleanup_loop(db_manager)
    )

    # Daily prune of video_queue history (done/skipped) past its retention window.
    _video_queue_history_task = asyncio.create_task(video_queue_history_retention_loop(db_manager))

    # Cache invalidation on DB writes from any process (this one, twitch, or
    # another API replica) — see shared/cache_invalidation.py. Dedicated
    # connections, independent of the pool, so they can start before it's ready.
    _config_change_listener_task = asyncio.create_task(
        pg_listen(settings.database_url, "config_change", _handle_config_change_notify)
    )
    _assistant_scope_listener_task = asyncio.create_task(
        pg_listen(
            settings.database_url,
            ASSISTANT_SCOPE_CHANGED_CHANNEL,
            handle_assistant_scope_changed_notify,
        )
    )
    _channel_toggle_listener_task = asyncio.create_task(
        pg_listen(settings.database_url, "channel_toggle", _handle_channel_toggle_notify)
    )
    # Safety net for pg_notify misses (dropped LISTEN connection, or a table
    # with no NOTIFY trigger at all — coverage is currently partial).
    _cache_clear_task = asyncio.create_task(_cache_clear_loop())
    _gauge_log_task = asyncio.create_task(_gauge_log_loop(db_manager))
    _twitch_authorization_task = asyncio.create_task(
        _twitch_authorization_loop(db_manager, settings)
    )

    notify_hub = get_notify_hub()
    notify_hub.start()

    yield

    # Shutdown
    LOGGER.info("Shutting down Niibot API server")
    _background_tasks = [
        _db_retry_task,
        _pool_heartbeat_task,
        _client_error_retention_task,
        _activation_cleanup_task,
        _community_overlay_cleanup_task,
        _video_queue_history_task,
        _config_change_listener_task,
        _assistant_scope_listener_task,
        _channel_toggle_listener_task,
        _cache_clear_task,
        _gauge_log_task,
        _twitch_authorization_task,
    ]
    for task in _background_tasks:
        if task:
            task.cancel()
    # Wait for cancellation to actually finish (e.g. pg_listen's connection.close())
    # before tearing down the pool it might still be touching.
    await asyncio.gather(*(t for t in _background_tasks if t), return_exceptions=True)
    try:
        await notify_hub.stop()
        await close_twitch_api()
        await close_bots_http_client()
        await close_command_import_http_client()
        await close_checkin_import_http_client()
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
            log_request_failure(request, code="HTTP.504", status=504, level=logging.WARNING)
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
            log_request_failure(request, code="INTERNAL.UNEXPECTED", status=500, exc=exc)
            return JSONResponse(
                status_code=500,
                content=build_envelope(
                    code="INTERNAL.UNEXPECTED",
                    message="系統暫時出了點狀況，請稍後再試",
                    request_id=rid,
                ),
            )

    # request context — accept upstream ID or generate; echoed on every
    # response, including the 500 / 504 built above. Binds the id (+ method
    # / path) into the log context so every line emitted while handling the
    # request carries it. clear_log_context() guards against a reused worker
    # leaking a previous request's user_id.
    @app.middleware("http")
    async def add_request_context(request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        clear_log_context()
        bind_log_context(
            request_id=request_id,
            http_method=request.method,
            http_path=request.url.path,
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # outermost — CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Cookie",
            "X-Request-ID",
            "X-Overlay-Key",
            "X-Niibot-Action",
        ],
        expose_headers=["X-Request-ID"],
    )

    # ── Exception handlers ──────────────────────────────────────────────
    # Run in Starlette's ExceptionMiddleware (inside every HTTP middleware),
    # so responses pass back out through CORS. Same set is installed on
    # throwaway apps in router tests. See core/error_handlers.py.
    register_exception_handlers(app)

    _activated = [Depends(require_activated)]

    # Register routers
    # Public / webhook routers — no activation gate
    app.include_router(discord_webhook_router.router)
    app.include_router(auth_router.router)
    app.include_router(bot_accounts_router.router)
    app.include_router(roleplay_router.router)
    app.include_router(ai_settings_router.tenant_router)
    app.include_router(channels_router.tenant_router)
    app.include_router(tenants_router.router)
    app.include_router(donation_router.router)
    app.include_router(client_errors_router.router)
    # Admin router — gated by stricter require_owner inside the router itself
    app.include_router(admin_router.router)
    # Fully-private routers — every endpoint requires an activated account
    app.include_router(channels_router.router, dependencies=_activated)
    app.include_router(checkin_router.router, dependencies=_activated)
    app.include_router(vip_router.router, dependencies=_activated)
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
    # Registered before commands_router so /api/commands/import/* is matched first, and
    # without the blanket activation dependency because the Nightbot OAuth callback is a
    # browser redirect that carries its identity in a signed state, not a JWT cookie.
    app.include_router(command_import_router.router)
    app.include_router(commands_router.router)
    app.include_router(game_queue_router.router)
    app.include_router(video_queue_router.router)
    app.include_router(crosshairs_router.router)
    app.include_router(community_overlay_router.router)

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
        """Readiness / status endpoint — includes DB health, build metadata,
        and runtime gauges (DB pool utilization + in-process cache sizes)."""
        db_ok = False
        gauges: dict = {"db_pool": None, "caches": {}}
        try:
            db_manager = get_database_manager()
            if db_manager.is_connected:
                db_ok = await db_manager.check_health()
            gauges = collect_runtime_gauges(db_manager)
        except RuntimeError:
            pass  # DB manager not yet initialized

        return {
            "service": "nb-api",
            "version": _APP_VERSION,
            "git_commit": _GIT_COMMIT,
            "started_at": _started_at,
            "environment": settings.environment,
            "uptime_seconds": int(time.time() - _start_time),
            "db_connected": db_ok,
            **gauges,
        }

    # Ping endpoint
    @app.api_route("/ping", methods=["GET", "HEAD"], response_class=PlainTextResponse)
    async def ping():
        """Ping endpoint"""
        return "pong"

    LOGGER.info("FastAPI application configured")

    return app
