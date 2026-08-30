"""Admin: read-only ad-hoc SQL console + schema browser (owner-only).

The console runs owner-supplied SELECTs, but never on the privileged application
connection's own authority: every query is executed inside a ``READ ONLY``
transaction *after* ``SET LOCAL ROLE niibot_db_console`` (migration 090), a role
with column-level SELECT grants that exclude every secret-bearing column. The
schema browser is driven off the same role's ``has_column_privilege`` so
protected columns are not even listed.
"""

import asyncio
import decimal
import logging
import re
import time
import uuid
from datetime import date, datetime

import asyncpg
from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.dependencies import get_db_pool, require_owner
from shared.errors import InvalidInputError

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter()

# The read-only role provisioned by migration 090. Queries and the schema
# browser both run with this identity so column-level grants are the single
# source of truth for what the console can see.
_CONSOLE_ROLE = "niibot_db_console"

_SELECT_RE = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
_DB_ROW_CAP = 500
_DB_TIMEOUT_MS = 5_000
_DB_TIMEOUT_S = _DB_TIMEOUT_MS / 1000
_SQL_MAX_LEN = 20_000


class DbQueryInvalidError(InvalidInputError):
    code = "ADMIN.DB_QUERY_INVALID"
    user_message = "查詢無法執行，請檢查語法"


class DbConsoleUnavailableError(InvalidInputError):
    code = "ADMIN.DB_CONSOLE_UNAVAILABLE"
    user_message = "資料庫查詢功能暫時無法使用，請稍後再試"


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


def _has_bare_semicolon(sql: str) -> bool:
    """True if a ``;`` appears outside a string literal (i.e. a second statement).

    A single trailing ``;`` has already been stripped by the caller. Anything
    left is either statement stacking or a literal ``;`` inside quotes — only the
    former should be rejected (with a clear message; the subquery wrapper would
    otherwise surface it as an opaque syntax error).
    """
    quote: str | None = None
    for ch in sql:
        if quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == ";":
            return True
    return False


class DbQueryRequest(BaseModel):
    sql: str


class DbQueryResponse(BaseModel):
    columns: list[str]
    rows: list[list]
    row_count: int
    duration_ms: float
    truncated: bool = False


class DbColumn(BaseModel):
    name: str
    type: str


class DbTable(BaseModel):
    name: str
    kind: str  # 'table' | 'view' | 'matview'
    approx_rows: int | None = None
    has_hidden_columns: bool = False  # some columns withheld by the console role
    is_empty: bool = False  # best-effort: no rows right now (hidden by default in UI)
    columns: list[DbColumn]


@router.post("/db/query", response_model=DbQueryResponse)
async def run_db_query(
    body: DbQueryRequest,
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> DbQueryResponse:
    """Execute one read-only SELECT against the database. Owner-only."""
    sql = body.sql.strip()
    if len(sql) > _SQL_MAX_LEN:
        raise DbQueryInvalidError(user_message="查詢內容過長")
    if not _SELECT_RE.match(sql):
        raise DbQueryInvalidError(user_message="只能執行 SELECT 查詢")
    sql = sql.rstrip().removesuffix(";").rstrip()
    if _has_bare_semicolon(sql):
        raise DbQueryInvalidError(user_message="一次只能執行一條查詢")

    # Wrapping in a subquery (rather than string-appending " LIMIT n") caps the
    # row count without the old _LIMIT_RE false-positive on an inner LIMIT, and
    # makes statement stacking a syntax error. Fetch one extra row to detect
    # truncation.
    wrapped = f"SELECT * FROM (\n{sql}\n) AS _q LIMIT {_DB_ROW_CAP + 1}"

    t0 = time.monotonic()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction(readonly=True):
                try:
                    await conn.execute(f"SET LOCAL ROLE {_CONSOLE_ROLE}")
                except asyncpg.PostgresError as e:
                    raise DbConsoleUnavailableError(
                        context={"reason": str(e), "hint": "apply migration 090"}
                    ) from e
                await conn.execute(f"SET LOCAL statement_timeout = {_DB_TIMEOUT_MS}")
                rows = await asyncio.wait_for(conn.fetch(wrapped), timeout=_DB_TIMEOUT_S + 3)
    except DbConsoleUnavailableError:
        raise
    except (TimeoutError, asyncpg.QueryCanceledError):
        LOGGER.warning(
            "db_console_query_failed",
            extra={"sql": sql[:500], "reason": "timeout"},
        )
        raise HTTPException(
            status_code=408, detail=f"Query timed out ({_DB_TIMEOUT_S:.0f}s limit)"
        ) from None
    except asyncpg.InsufficientPrivilegeError as e:
        LOGGER.warning(
            "db_console_query_failed",
            extra={"sql": sql[:500], "reason": "insufficient_privilege"},
        )
        raise DbQueryInvalidError(user_message="這個資料表或欄位是受保護的內容，無法查詢") from e
    except Exception as e:
        LOGGER.warning("db_console_query_failed", extra={"sql": sql[:500], "reason": str(e)})
        raise DbQueryInvalidError(
            user_message="查詢失敗，請檢查語法", context={"reason": str(e)}
        ) from e

    duration_ms = (time.monotonic() - t0) * 1000
    truncated = len(rows) > _DB_ROW_CAP
    if truncated:
        rows = rows[:_DB_ROW_CAP]

    columns = list(rows[0].keys()) if rows else []
    result_rows = [[_json_safe(v) for v in row] for row in rows]
    LOGGER.info(
        "db_console_query",
        extra={
            "sql": sql[:500],
            "row_count": len(result_rows),
            "duration_ms": round(duration_ms, 1),
            "truncated": truncated,
        },
    )
    return DbQueryResponse(
        columns=columns,
        rows=result_rows,
        row_count=len(result_rows),
        duration_ms=duration_ms,
        truncated=truncated,
    )


_SCHEMA_SQL = """
SELECT c.relname                                        AS table_name,
       c.relkind                                        AS relkind,
       a.attname                                        AS column_name,
       format_type(a.atttypid, a.atttypmod)             AS data_type,
       CASE WHEN c.relkind = 'r'
            THEN c.reltuples::bigint END                AS approx_rows,
       has_column_privilege($1, c.oid, a.attnum, 'SELECT') AS can_select
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid
                   AND a.attnum > 0
                   AND NOT a.attisdropped
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'v', 'm')
ORDER BY c.relname, a.attnum
"""

_RELKIND = {"r": "table", "v": "view", "m": "matview"}


@router.get("/db/schema", response_model=list[DbTable])
async def get_db_schema(
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> list[DbTable]:
    """List every table/view the console role may read, with column types.

    Owner-only. Filtered by ``has_column_privilege`` for ``niibot_db_console``,
    so a column the role cannot SELECT never appears. ``is_empty`` is a
    best-effort ``EXISTS`` probe per relation (``reltuples`` is unreliable until
    a table is analyzed); the UI hides empty relations by default.
    """
    try:
        async with pool.acquire() as conn:
            records = await conn.fetch(_SCHEMA_SQL, _CONSOLE_ROLE)

            tables: dict[str, DbTable] = {}
            for r in records:
                t = tables.get(r["table_name"])
                if t is None:
                    t = DbTable(
                        name=r["table_name"],
                        kind=_RELKIND.get(r["relkind"], r["relkind"]),
                        approx_rows=(
                            int(r["approx_rows"]) if r["approx_rows"] is not None else None
                        ),
                        columns=[],
                    )
                    tables[r["table_name"]] = t
                if r["can_select"]:
                    t.columns.append(DbColumn(name=r["column_name"], type=r["data_type"]))
                else:
                    t.has_hidden_columns = True

            # Drop anything the role cannot read a single column of.
            result = [t for t in tables.values() if t.columns]
            await _mark_empty(conn, result)
            return result
    except asyncpg.UndefinedObjectError as e:  # role absent → migration 090 unapplied
        raise DbConsoleUnavailableError(
            context={"reason": str(e), "hint": "apply migration 090"}
        ) from e


def _qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


async def _mark_empty(conn: asyncpg.Connection, tables: list[DbTable]) -> None:
    """Set ``is_empty`` via one batched EXISTS probe, running as the console role.

    Best-effort: any failure (role missing, permission, timeout) leaves every
    ``is_empty`` False so the UI shows all relations rather than hiding wrongly.
    """
    if not tables:
        return
    probe = " UNION ALL ".join(
        f"SELECT {i} AS idx, EXISTS(SELECT 1 FROM {_qident(t.name)}) AS has_rows"
        for i, t in enumerate(tables)
    )
    try:
        async with conn.transaction(readonly=True):
            await conn.execute(f"SET LOCAL ROLE {_CONSOLE_ROLE}")
            await conn.execute("SET LOCAL statement_timeout = 4000")
            rows = await conn.fetch(probe)
    except asyncpg.PostgresError as e:
        LOGGER.warning("db_console_schema_empty_probe_failed", extra={"reason": str(e)})
        return
    for r in rows:
        if not r["has_rows"]:
            tables[r["idx"]].is_empty = True
