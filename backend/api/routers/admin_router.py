"""Admin-only API routes — accessible only to the bot owner."""

import asyncio
import decimal
import logging
import re
import struct
import time
import uuid
from datetime import date, datetime

import aiohttp
from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.config import get_settings
from core.dependencies import (
    get_channel_service,
    get_current_channel_id,
    get_db_pool,
    get_twitch_api,
)
from services import ChannelService, TwitchAPIClient
from shared.repositories.activation_code import ActivationCodeRepository
from shared.repositories.activation_request import ActivationRequestRepository

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def require_owner(channel_id: str = Depends(get_current_channel_id)) -> str:
    if channel_id != str(get_settings().owner_id):
        raise HTTPException(status_code=403, detail="Owner access required")
    return channel_id


class AdminChannelInfo(BaseModel):
    id: str
    name: str
    display_name: str
    avatar: str
    is_live: bool
    mod_status: str  # 'mod' | 'no_mod' | 'token_error' | 'scope_error'


@router.get("/channels", response_model=list[AdminChannelInfo])
async def get_admin_channels(
    owner_id: str = Depends(require_owner),
    channel_service: ChannelService = Depends(get_channel_service),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> list[AdminChannelInfo]:
    """Return all monitored channels with mod status. Owner-only."""
    enabled = await channel_service.get_enabled_channels()
    other = [ch for ch in enabled if ch["channel_id"] != owner_id]
    if not other:
        return []

    channel_ids = [ch["channel_id"] for ch in other]
    bot_id = get_settings().bot_id or ""

    users_data, streams_data = await asyncio.gather(
        twitch_api.get_users_by_ids(channel_ids),
        twitch_api.get_streams(channel_ids),
    )
    live_ids = {s["user_id"] for s in streams_data}
    user_map = {u["id"]: u for u in users_data}

    async def _check_mod(channel_id: str) -> tuple[str, str]:
        if not bot_id:
            return channel_id, "token_error"
        token = await channel_service.get_token_with_refresh(channel_id, twitch_api)
        if not token:
            return channel_id, "token_error"
        status = await twitch_api.get_bot_mod_status(channel_id, bot_id, token)
        return channel_id, status

    mod_results = await asyncio.gather(
        *[_check_mod(cid) for cid in channel_ids], return_exceptions=True
    )
    mod_map: dict[str, str] = {}
    for r in mod_results:
        if isinstance(r, Exception):
            LOGGER.warning("mod status check failed for a channel: %s", r)
        else:
            cid, status = r  # type: ignore[misc]
            mod_map[cid] = status

    result = [
        AdminChannelInfo(
            id=cid,
            name=user_map.get(cid, {}).get("login", ""),
            display_name=user_map.get(cid, {}).get("display_name", ""),
            avatar=user_map.get(cid, {}).get("profile_image_url", ""),
            is_live=cid in live_ids,
            mod_status=mod_map.get(cid, "error"),
        )
        for ch in other
        if (cid := ch["channel_id"]) and cid in user_map
    ]

    result.sort(key=lambda x: (x.mod_status != "mod", x.name))
    return result


class PendingCodeInfo(BaseModel):
    platform_user_id: str
    display_name: str | None
    username: str | None
    avatar: str | None
    expires_at: datetime
    code_plain: str | None


class ActivationRequestInfo(BaseModel):
    id: int
    platform_user_id: str
    display_name: str | None
    username: str | None
    avatar: str | None
    note: str
    created_at: datetime


@router.get("/activation-codes", response_model=list[PendingCodeInfo])
async def get_pending_activation_codes(
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> list[PendingCodeInfo]:
    """List unused, non-expired OTP activation codes. Owner-only."""
    rows = await pool.fetch(
        """
        SELECT ac.platform_user_id, ac.expires_at, ac.code_plain,
               u.display_name, u.avatar, ula.username
        FROM activation_codes ac
        LEFT JOIN user_linked_accounts ula
            ON ula.platform = ac.platform AND ula.platform_user_id = ac.platform_user_id
        LEFT JOIN users u ON u.id = ula.user_id
        WHERE ac.used_at IS NULL AND ac.expires_at > NOW()
        ORDER BY ac.expires_at ASC
        """
    )
    return [PendingCodeInfo(**dict(r)) for r in rows]


@router.delete("/activation-codes/{platform_user_id}")
async def revoke_activation_code(
    platform_user_id: str,
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> dict:
    """Invalidate an unused activation code for a user. Owner-only."""
    repo = ActivationCodeRepository(pool)
    if not await repo.invalidate("twitch", platform_user_id):
        raise HTTPException(status_code=404, detail="No active code found for this user")
    LOGGER.info(f"Activation code revoked for {platform_user_id}")
    return {"revoked": True}


@router.get("/activation-requests", response_model=list[ActivationRequestInfo])
async def get_activation_requests(
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> list[ActivationRequestInfo]:
    """List pending manual activation requests. Owner-only."""
    repo = ActivationRequestRepository(pool)
    rows = await repo.list_pending()
    return [ActivationRequestInfo(**r) for r in rows]


@router.post("/activation-requests/{request_id}/approve")
async def approve_activation_request(
    request_id: int,
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> dict:
    """Approve a manual activation request, activating the user. Owner-only."""
    repo = ActivationRequestRepository(pool)
    if not await repo.approve(request_id):
        raise HTTPException(status_code=404, detail="Request not found or already reviewed")
    LOGGER.info(f"Activation request {request_id} approved by owner")
    return {"approved": True}


_DOCKER_SOCKET = "/var/run/docker.sock"
_KNOWN_CONTAINERS = [
    {"name": "niibot-api", "label": "API Server"},
    {"name": "niibot-twitch", "label": "Twitch Bot"},
    {"name": "niibot-discord", "label": "Discord Bot"},
    {"name": "niibot-postgres", "label": "PostgreSQL"},
    {"name": "niibot-scrapling", "label": "Scrapling"},
    {"name": "niibot-instafix", "label": "Instafix"},
]
_ALLOWED_CONTAINERS = {c["name"] for c in _KNOWN_CONTAINERS}


class LogContainerInfo(BaseModel):
    name: str
    label: str
    running: bool


class LogLine(BaseModel):
    stream: str  # 'stdout' | 'stderr'
    text: str


class ContainerLogsResponse(BaseModel):
    container: str
    lines: list[LogLine]


def _parse_docker_stream(raw: bytes) -> list[LogLine]:
    lines: list[LogLine] = []
    i = 0
    while i + 8 <= len(raw):
        stream_type = raw[i]
        size = struct.unpack(">I", raw[i + 4 : i + 8])[0]
        if i + 8 + size > len(raw):
            break
        payload = raw[i + 8 : i + 8 + size].decode("utf-8", errors="replace")
        for line in payload.split("\n"):
            stripped = line.rstrip("\r")
            if stripped:
                lines.append(
                    LogLine(stream="stderr" if stream_type == 2 else "stdout", text=stripped)
                )
        i += 8 + size
    return lines


@router.get("/logs/containers", response_model=list[LogContainerInfo])
async def list_log_containers(
    _: str = Depends(require_owner),
) -> list[LogContainerInfo]:
    """List known Docker containers with running status. Owner-only."""
    try:
        connector = aiohttp.UnixConnector(path=_DOCKER_SOCKET)
        async with aiohttp.ClientSession(connector=connector) as session:
            result: list[LogContainerInfo] = []
            for c in _KNOWN_CONTAINERS:
                try:
                    async with session.get(
                        f"http://localhost/v1.41/containers/{c['name']}/json"
                    ) as resp:
                        running = False
                        if resp.status == 200:
                            data = await resp.json()
                            running = data.get("State", {}).get("Running", False)
                        result.append(LogContainerInfo(**c, running=running))
                except Exception:
                    result.append(LogContainerInfo(**c, running=False))
            return result
    except Exception as e:
        LOGGER.warning(f"Docker socket unavailable for container list: {e}")
        return [LogContainerInfo(**c, running=False) for c in _KNOWN_CONTAINERS]


@router.get("/logs/{container}", response_model=ContainerLogsResponse)
async def get_container_logs(
    container: str,
    tail: int = Query(default=200, ge=10, le=2000),
    since: float | None = Query(
        default=None, description="Unix timestamp — fetch only logs after this time"
    ),
    _: str = Depends(require_owner),
) -> ContainerLogsResponse:
    """Fetch logs from a Docker container. Owner-only."""
    if container not in _ALLOWED_CONTAINERS:
        raise HTTPException(status_code=400, detail="Unknown container")

    params = "?stdout=1&stderr=1&timestamps=1"
    if since is not None:
        params += f"&since={since}"
    else:
        params += f"&tail={tail}"

    try:
        connector = aiohttp.UnixConnector(path=_DOCKER_SOCKET)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(
                f"http://localhost/v1.41/containers/{container}/logs{params}"
            ) as resp:
                if resp.status == 404:
                    raise HTTPException(status_code=404, detail="Container not found")
                if resp.status != 200:
                    raise HTTPException(status_code=502, detail=f"Docker API error: {resp.status}")
                raw = await resp.read()
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.warning(f"Docker socket unavailable for logs({container}): {e}")
        raise HTTPException(status_code=503, detail="Docker socket unavailable") from e

    return ContainerLogsResponse(container=container, lines=_parse_docker_stream(raw))


_SELECT_RE = re.compile(
    r"^\s*(?:--[^\n]*\n\s*|/\*.*?\*/\s*)*(SELECT|WITH)\b",
    re.IGNORECASE | re.DOTALL,
)
_LIMIT_RE = re.compile(r"\bLIMIT\s+\d+", re.IGNORECASE)
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
        raise HTTPException(
            status_code=400, detail="Only SELECT (or WITH … SELECT) queries are allowed"
        )

    if not _LIMIT_RE.search(sql):
        sql = f"{sql} LIMIT {_DB_ROW_CAP}"

    t0 = time.monotonic()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction(readonly=True):
                rows = await asyncio.wait_for(conn.fetch(sql), timeout=_DB_TIMEOUT)
    except TimeoutError:
        raise HTTPException(
            status_code=408, detail=f"Query timed out ({_DB_TIMEOUT:.0f}s limit)"
        ) from None
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

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


@router.post("/activation-requests/{request_id}/reject")
async def reject_activation_request(
    request_id: int,
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> dict:
    """Reject a manual activation request. Owner-only."""
    repo = ActivationRequestRepository(pool)
    if not await repo.reject(request_id):
        raise HTTPException(status_code=404, detail="Request not found or already reviewed")
    LOGGER.info(f"Activation request {request_id} rejected by owner")
    return {"rejected": True}
