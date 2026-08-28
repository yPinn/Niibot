"""Admin: Docker container log access (owner-only)."""

import json
import logging
import re
import struct
from typing import Any, Literal

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.config import get_settings
from core.dependencies import require_owner

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter()

_DOCKER_SOCKET = "/var/run/docker.sock"

# Per-environment container name suffix. Prod and staging share the docker host,
# so the staging API must NOT query bare names like "nb-api" — those resolve to
# prod containers. docker-compose.staging.yml suffixes every service with "-stg".
_CONTAINER_SUFFIX_BY_ENV = {"staging": "-stg"}

_CONTAINER_BASES = [
    ("nb-api", "API Server"),
    ("nb-twitch", "Twitch Bot"),
    ("nb-discord", "Discord Bot"),
    ("nb-pg", "PostgreSQL"),
    ("nb-instafix", "Instafix"),
]


def _known_containers() -> list[dict[str, str]]:
    suffix = _CONTAINER_SUFFIX_BY_ENV.get(get_settings().environment, "")
    return [{"name": f"{base}{suffix}", "label": label} for base, label in _CONTAINER_BASES]


def _allowed_containers() -> set[str]:
    return {c["name"] for c in _known_containers()}


class LogContainerInfo(BaseModel):
    name: str
    label: str
    running: bool


class LogLine(BaseModel):
    stream: str  # 'stdout' | 'stderr'
    text: str


class LogRecordOut(BaseModel):
    """A single log line, parsed. `source` says how it was recognised;
    `raw` is always the original text for copy / fallback rendering."""

    stream: str
    ts: str = ""
    level: str = "UNKNOWN"  # DEBUG|INFO|WARNING|ERROR|CRITICAL|UNKNOWN
    source: Literal["json", "postgres", "raw"]
    message: str
    logger: str = ""
    mod: str = ""
    own: bool = False
    service: str = ""
    request_id: str | None = None
    channel: str | None = None
    code: str | None = None
    pid: str | None = None
    exception: str | None = None
    extra: dict[str, Any] = {}
    raw: str


class ContainerLogsResponse(BaseModel):
    container: str
    records: list[LogRecordOut]


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


# ── Line → record parsing ──────────────────────────────────────────────────

# Docker's `timestamps=1` prefix: RFC3339 + space + payload
_DOCKER_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})\.\S+\s(.*)$", re.DOTALL)
# Postgres own prefix: "2026-05-15 01:39:23.531 UTC [28] LOG:  ..." — the
# timezone token depends on the container's log_timezone, so keep it loose.
_PG_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+ [A-Z]{2,5} \[(\d+)\] ([A-Z]+):\s*(.*)$",
    re.DOTALL,
)
_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_ERR_KW = re.compile(r"\b(ERROR|CRITICAL|FATAL|EXCEPTION|TRACEBACK)\b", re.IGNORECASE)
_WARN_KW = re.compile(r"\bWARN(ING)?\b", re.IGNORECASE)
_DEBUG_KW = re.compile(r"\bDEBUG\b", re.IGNORECASE)

_LEVEL_ORDER = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 3}
_JSON_KNOWN = {
    "timestamp",
    "level",
    "logger",
    "mod",
    "own",
    "service",
    "event",
    "request_id",
    "channel",
    "channel_id",
    "code",
    "exception",
    "http_method",
    "http_path",
    "user_id",
}


def _s(v: Any) -> str | None:
    return str(v) if v is not None and v != "" else None


def _guess_level(text: str) -> str:
    if _ERR_KW.search(text):
        return "ERROR"
    if _WARN_KW.search(text):
        return "WARNING"
    if _DEBUG_KW.search(text):
        return "DEBUG"
    return "UNKNOWN"


def _pg_level(lvl: str) -> str:
    if lvl in {"ERROR", "FATAL", "PANIC"}:
        return "ERROR"
    if lvl == "WARNING":
        return "WARNING"
    if lvl == "DEBUG":
        return "DEBUG"
    return "INFO"


def _record_from_line(line: LogLine) -> LogRecordOut:
    raw = line.text
    ts, body = "", raw
    m = _DOCKER_TS_RE.match(raw)
    if m:
        ts = f"{m.group(1)} {m.group(2)}"
        body = m.group(3)

    stripped = body.lstrip()
    if stripped.startswith("{"):
        try:
            d = json.loads(stripped)
        except ValueError:
            d = None
        if isinstance(d, dict):
            lvl = str(d.get("level", "")).upper()
            return LogRecordOut(
                stream=line.stream,
                ts=ts or str(d.get("timestamp", "")),
                level=lvl if lvl in _LEVELS else "INFO",
                source="json",
                message=str(d.get("event", "")),
                logger=str(d.get("logger", "")),
                mod=str(d.get("mod", "")),
                own=bool(d.get("own", False)),
                service=str(d.get("service", "")),
                request_id=_s(d.get("request_id")),
                channel=_s(d.get("channel") or d.get("channel_id")),
                code=_s(d.get("code")),
                exception=_s(d.get("exception")),
                extra={k: v for k, v in d.items() if k not in _JSON_KNOWN},
                raw=raw,
            )

    pg = _PG_RE.match(body)
    if pg:
        return LogRecordOut(
            stream=line.stream,
            ts=ts or pg.group(1),
            level=_pg_level(pg.group(3)),
            source="postgres",
            pid=pg.group(2),
            message=pg.group(4),
            raw=raw,
        )

    return LogRecordOut(
        stream=line.stream,
        ts=ts,
        level=_guess_level(body),
        source="raw",
        message=body,
        raw=raw,
    )


def _to_records(
    lines: list[LogLine], *, level: str = "ALL", q: str | None = None
) -> list[LogRecordOut]:
    threshold = _LEVEL_ORDER.get(level.upper()) if level.upper() != "ALL" else None
    needle = q.lower() if q else None
    out: list[LogRecordOut] = []
    for line in lines:
        rec = _record_from_line(line)
        if threshold is not None:
            rank = _LEVEL_ORDER.get(rec.level)
            # unrecognised level (traceback continuations, third-party) always shows
            if rank is not None and rank < threshold:
                continue
        if needle and needle not in rec.message.lower() and needle not in rec.raw.lower():
            continue
        out.append(rec)
    return out


@router.get("/logs/containers", response_model=list[LogContainerInfo])
async def list_log_containers(
    _: str = Depends(require_owner),
) -> list[LogContainerInfo]:
    """List known Docker containers with running status. Owner-only."""
    known = _known_containers()
    try:
        connector = aiohttp.UnixConnector(path=_DOCKER_SOCKET)
        async with aiohttp.ClientSession(connector=connector) as session:
            result: list[LogContainerInfo] = []
            for c in known:
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
        LOGGER.warning("Docker socket unavailable for container list: %s", e)
        return [LogContainerInfo(**c, running=False) for c in known]


@router.get("/logs/{container}", response_model=ContainerLogsResponse)
async def get_container_logs(
    container: str,
    tail: int = Query(default=200, ge=10, le=2000),
    since: float | None = Query(
        default=None, description="Unix timestamp — fetch only logs after this time"
    ),
    level: str = Query(default="ALL", pattern="^(ALL|DEBUG|INFO|WARNING|ERROR)$"),
    q: str | None = Query(default=None, max_length=200),
    _: str = Depends(require_owner),
) -> ContainerLogsResponse:
    """Fetch logs from a Docker container. Owner-only."""
    if container not in _allowed_containers():
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
        LOGGER.warning("Docker socket unavailable for logs(%s): %s", container, e)
        raise HTTPException(status_code=503, detail="Docker socket unavailable") from e

    lines = _parse_docker_stream(raw)
    return ContainerLogsResponse(
        container=container,
        records=_to_records(lines, level=level, q=q),
    )
