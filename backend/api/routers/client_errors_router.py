"""Public sink for frontend error telemetry — POST /api/client-errors.

Deliberately unauthenticated: the errors we most need to see happen on
landing / login / donate / overlay pages where there is no session.

Abuse is bounded by (1) per-IP and per-(IP,fingerprint) rate limits,
(2) Pydantic field-length caps, (3) a 32 KB body ceiling, and (4) CORS
being restricted to the configured frontend origin.

The endpoint ALWAYS returns 202 with an empty body and never raises — a
non-2xx here could make the frontend reporter treat the failure as a new
error and loop.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import date

from asyncpg import Pool
from fastapi import APIRouter, Cookie, Depends, Request, Response
from pydantic import BaseModel, Field, ValidationError

from core.dependencies import get_auth_service, get_db_pool
from core.rate_limit import RateLimiter
from services.auth_service import AuthService
from shared.repositories.client_error import ClientErrorRepository

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/client-errors", tags=["telemetry"])

_MAX_BODY_BYTES = 32_768
_per_ip = RateLimiter(max_calls=20, period=60.0)
_per_fingerprint = RateLimiter(max_calls=3, period=300.0)


class ClientErrorIn(BaseModel):
    kind: str = Field(pattern="^(error|unhandledrejection|react|api)$")
    fingerprint: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2000)
    url: str = Field(min_length=1, max_length=2000)
    stack: str | None = Field(default=None, max_length=8000)
    component_stack: str | None = Field(default=None, max_length=4000)
    route: str | None = Field(default=None, max_length=200)
    request_id: str | None = Field(default=None, max_length=100)
    error_code: str | None = Field(default=None, max_length=80)
    http_status: int | None = Field(default=None, ge=100, le=599)
    app_version: str | None = Field(default=None, max_length=50)


def _ip_hash(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    return hashlib.sha256(f"{ip}|{date.today().isoformat()}".encode()).hexdigest()


def _best_effort_user_id(auth_token: str | None, auth: AuthService) -> str | None:
    if not auth_token:
        return None
    try:
        payload = auth.verify_token(auth_token)
    except Exception:
        return None
    sub = (payload or {}).get("sub")
    return str(sub) if sub else None


@router.post("", status_code=202)
async def report_client_error(
    request: Request,
    response: Response,
    auth_token: str | None = Cookie(default=None),
    pool: Pool = Depends(get_db_pool),
    auth: AuthService = Depends(get_auth_service),
) -> Response:
    """Record one frontend error. Always 202; never raises."""
    response.status_code = 202
    try:
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > _MAX_BODY_BYTES:
            return response

        raw = await request.body()
        if len(raw) > _MAX_BODY_BYTES:
            return response

        try:
            data = ClientErrorIn.model_validate_json(raw)
        except ValidationError:
            return response

        ip = request.client.host if request.client else "unknown"
        if not _per_ip.allow(ip) or not _per_fingerprint.allow(f"{ip}|{data.fingerprint}"):
            return response

        repo = ClientErrorRepository(pool)
        await repo.insert(
            kind=data.kind,
            fingerprint=data.fingerprint,
            message=data.message,
            url=data.url,
            stack=data.stack,
            component_stack=data.component_stack,
            route=data.route,
            request_id=data.request_id,
            error_code=data.error_code,
            http_status=data.http_status,
            user_id=_best_effort_user_id(auth_token, auth),
            user_agent=request.headers.get("user-agent", "")[:500] or None,
            app_version=data.app_version,
            ip_hash=_ip_hash(request),
        )
    except Exception:
        LOGGER.exception("client_error_report_failed")
    return response


async def client_error_retention_loop(db_manager) -> None:
    """Delete client_errors rows past the retention window, once a day."""
    while True:
        try:
            await asyncio.sleep(86_400)
            if not db_manager.is_connected:
                continue
            removed = await ClientErrorRepository(db_manager.pool).prune_old()
            if removed:
                LOGGER.info("client_errors_pruned", extra={"rows": removed})
        except asyncio.CancelledError:
            return
        except Exception:
            LOGGER.exception("client_errors_prune_failed")
