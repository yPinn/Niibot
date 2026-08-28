"""Admin: read-only ad-hoc SQL query endpoint (owner-only)."""

import asyncio
import decimal
import logging
import re
import time
import uuid
from datetime import date, datetime

from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.dependencies import get_db_pool, require_owner
from shared.errors import InvalidInputError

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter()


class DbQueryInvalidError(InvalidInputError):
    code = "ADMIN.DB_QUERY_INVALID"
    user_message = "查詢無法執行，請檢查語法"


_LIMIT_RE = re.compile(r"\bLIMIT\s+\d+", re.IGNORECASE)
_SELECT_RE = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
_DB_ROW_CAP = 500
_DB_TIMEOUT = 5.0


def _json_safe(val: object) -> object:
    if val is None or isinstance(val, (bool, int, float, str)):
        return val
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, decimal.Decimal):
        return float(val)
    if isinstance(val, uuid.UUID):
        return str(val)
    return str(val)


class DbQueryRequest(BaseModel):
    sql: str


class DbQueryResponse(BaseModel):
    columns: list[str]
    rows: list[list]
    row_count: int
    duration_ms: float


@router.post("/db/query", response_model=DbQueryResponse)
async def run_db_query(
    body: DbQueryRequest,
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> DbQueryResponse:
    """Execute a read-only SELECT query against the database. Owner-only."""
    sql = body.sql.strip()
    if not _SELECT_RE.match(sql):
        raise DbQueryInvalidError(user_message="只能執行 SELECT 查詢")
    if not _LIMIT_RE.search(sql):
        sql = f"{sql} LIMIT {_DB_ROW_CAP}"

    t0 = time.monotonic()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction(readonly=True):
                rows = await asyncio.wait_for(conn.fetch(sql), timeout=_DB_TIMEOUT)
    except TimeoutError:
        # 408 is not an AppError-allowed status; keep it as a bare HTTPException.
        raise HTTPException(
            status_code=408, detail=f"Query timed out ({_DB_TIMEOUT:.0f}s limit)"
        ) from None
    except Exception as e:
        raise DbQueryInvalidError(
            user_message="查詢失敗，請檢查語法", context={"reason": str(e)}
        ) from e

    duration_ms = (time.monotonic() - t0) * 1000

    if not rows:
        return DbQueryResponse(columns=[], rows=[], row_count=0, duration_ms=duration_ms)

    columns = list(rows[0].keys())
    result_rows = [[_json_safe(v) for v in row] for row in rows]
    return DbQueryResponse(
        columns=columns,
        rows=result_rows,
        row_count=len(result_rows),
        duration_ms=duration_ms,
    )
