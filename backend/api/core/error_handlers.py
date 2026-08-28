"""FastAPI exception handlers and the shared request-failure logger.

Kept in its own module so router tests can install the exact same handlers
on their throwaway apps via ``register_exception_handlers(app)``.

Every handler emits the same body shape as ``shared.errors.build_envelope``:
``{"detail": <msg>, "error": {"code", "message", "request_id", "fields"}}``.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from shared.errors import AppError, build_envelope

LOGGER: logging.Logger = logging.getLogger(__name__)

_GENERIC_500 = "系統暫時出了點狀況，請稍後再試"


def log_request_failure(
    request: Request,
    *,
    code: str,
    status: int,
    exc: BaseException | None = None,
    level: int = logging.ERROR,
    context: dict | None = None,
) -> None:
    """One structured 'request_failed' line. request_id / user_id / channel_id
    come from the log context bound by middleware, not from here."""
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


def _rid(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    log_request_failure(
        request,
        code=exc.code,
        status=exc.http_status,
        exc=exc,
        level=exc.log_level,
        context=exc.context,
    )
    return JSONResponse(status_code=exc.http_status, content=exc.to_envelope(_rid(request)))


async def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
    log_request_failure(
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
            request_id=_rid(request),
        ),
    )


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail else "請求無法處理"
    if exc.status_code >= 500:
        log_request_failure(
            request, code=f"HTTP.{exc.status_code}", status=exc.status_code, exc=exc
        )
    return JSONResponse(
        status_code=exc.status_code,
        content=build_envelope(
            code=f"HTTP.{exc.status_code}", message=detail, request_id=_rid(request)
        ),
        headers=exc.headers,
    )


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    log_request_failure(request, code="INTERNAL.UNEXPECTED", status=500, exc=exc)
    return JSONResponse(
        status_code=500,
        content=build_envelope(
            code="INTERNAL.UNEXPECTED", message=_GENERIC_500, request_id=_rid(request)
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Wire the four handlers. Call from create_app() and from router tests."""
    app.add_exception_handler(AppError, _handle_app_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _handle_validation)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _handle_unexpected)
