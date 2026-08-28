"""Admin: frontend error-telemetry viewer (owner-only).

Reads the ``client_errors`` sink (migration 085). The list endpoint aggregates
by fingerprint so a recurring bug is one row; the detail endpoint returns the
raw events for a fingerprint, including stack traces.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from asyncpg import Pool
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from core.dependencies import get_db_pool, require_owner
from shared.repositories.client_error import ClientErrorRepository

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter()


class ClientErrorGroup(BaseModel):
    fingerprint: str
    count: int
    first_seen: datetime
    last_seen: datetime
    kind: str
    message: str
    route: str | None = None
    error_code: str | None = None
    http_status: int | None = None
    app_version: str | None = None
    request_id: str | None = None


class ClientErrorEvent(BaseModel):
    occurred_at: datetime
    kind: str
    message: str
    stack: str | None = None
    component_stack: str | None = None
    url: str
    route: str | None = None
    request_id: str | None = None
    error_code: str | None = None
    http_status: int | None = None
    user_id: str | None = None
    user_agent: str | None = None
    app_version: str | None = None


def _row(record: Any) -> dict[str, Any]:
    d = dict(record)
    if d.get("user_id") is not None:
        d["user_id"] = str(d["user_id"])
    return d


@router.get("/client-errors", response_model=list[ClientErrorGroup])
async def list_client_errors(
    since_hours: int = Query(default=168, ge=1, le=336),
    kind: str | None = Query(default=None, pattern="^(error|unhandledrejection|react|api)$"),
    limit: int = Query(default=100, ge=1, le=500),
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> list[ClientErrorGroup]:
    """Recent frontend errors, grouped by fingerprint. Owner-only."""
    rows = await ClientErrorRepository(pool).list_grouped(
        since_hours=since_hours, kind=kind, limit=limit
    )
    return [ClientErrorGroup(**_row(r)) for r in rows]


@router.get("/client-errors/{fingerprint}", response_model=list[ClientErrorEvent])
async def get_client_error_events(
    fingerprint: str,
    limit: int = Query(default=50, ge=1, le=200),
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> list[ClientErrorEvent]:
    """Raw events for one fingerprint, newest first. Owner-only."""
    rows = await ClientErrorRepository(pool).list_by_fingerprint(fingerprint, limit=limit)
    return [ClientErrorEvent(**_row(r)) for r in rows]
