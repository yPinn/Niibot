"""Admin: Docker container log access (owner-only)."""

import json
import logging
import re
import struct
from collections.abc import Mapping
from typing import Any, Literal

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.config import get_settings
from core.database import get_database_manager
from core.dependencies import require_owner
from shared.repositories.channel import ChannelRepository

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter()

_DOCKER_SOCKET = "/var/run/docker.sock"

_PROJECT_ENV = {"development": "dev", "staging": "stg", "production": "prod"}
_CONTAINER_SERVICES = [
    ("api", "API Server"),
    ("twitch-bot", "Twitch Bot"),
    ("discord-bot", "Discord Bot"),
    ("postgres", "PostgreSQL"),
    ("instafix", "Instafix"),
]


def _known_containers() -> list[dict[str, str]]:
    env = _PROJECT_ENV[get_settings().environment]
    return [
        {"name": f"niibot-{env}-{service}-1", "label": label}
        for service, label in _CONTAINER_SERVICES
    ]


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
    source: Literal["json", "postgres", "raw", "console"]
    message: str
    logger: str = ""
    mod: str = ""
    own: bool = False
    service: str = ""
    request_id: str | None = None
    channel: str | None = None
    #: Login resolved from a numeric `channel`, so reading a log doesn't
    #: require a manual SQL lookup to find out whose channel broke. Only set
    #: when `channel` is a numeric id we could resolve; `channel` itself is
    #: left untouched so the id is still available.
    channel_name: str | None = None
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

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# structlog's dev ConsoleRenderer line (`console=True`). After ANSI strip:
#   <iso-ts> [<level>   ] <event> [<logger>] key=value key=value ...
# `_add_meta` always appends `mod`/`own`/`service`, so a genuine line from our
# pipeline always ends with a `key=value` block containing `service=`.
_CONSOLE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T[\d:.]+(?:Z|[+-]\d{2}:?\d{2})?) \[([A-Za-z]+)\s*\] (.*)$",
    re.DOTALL,
)
_CONSOLE_TAIL_RE = re.compile(r"^(.*?)\s+\[([\w.]+)\]\s+(\S.*)$", re.DOTALL)
_KV_RE = re.compile(r"(\w+)=('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|\S+)")
_CONSOLE_KNOWN = {"mod", "own", "service", "request_id", "channel", "channel_id", "code"}

_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
# `(?<!=)` so a `key=error` / `key=debug` value in a structured tail never trips
# the heuristic (it only ever runs on genuinely unstructured lines now).
_ERR_KW = re.compile(r"(?<!=)\b(ERROR|CRITICAL|FATAL|EXCEPTION|TRACEBACK)\b", re.IGNORECASE)
_WARN_KW = re.compile(r"(?<!=)\bWARN(ING)?\b", re.IGNORECASE)
_DEBUG_KW = re.compile(r"(?<!=)\bDEBUG\b", re.IGNORECASE)

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


def _unquote(v: str) -> str:
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    return v


def _parse_console(body: str, stream: str, docker_ts: str, raw: str) -> LogRecordOut | None:
    """Decode a structlog ConsoleRenderer line into a structured record.

    Returns None for anything that isn't one — the caller then falls back to the
    raw-line heuristic. Dev runs with ``console=True``; without this the whole
    line (embedded ts, ``[level]`` and the ``key=value`` tail) lands as ``raw``
    and ``_guess_level`` mis-reads e.g. ``mod=error`` as an ERROR.
    """
    m = _CONSOLE_RE.match(_ANSI_RE.sub("", body))
    if not m:
        return None
    iso_ts, level_raw, rest = m.group(1), m.group(2).upper(), m.group(3)
    tail = _CONSOLE_TAIL_RE.match(rest)
    if not tail:
        return None
    event, logger = tail.group(1), tail.group(2)
    kv = {k: _unquote(v) for k, v in _KV_RE.findall(tail.group(3))}
    if "service" not in kv:  # not our pipeline's format — leave it to the raw path
        return None
    return LogRecordOut(
        stream=stream,
        ts=docker_ts or iso_ts,
        level=level_raw if level_raw in _LEVELS else "INFO",
        source="console",
        message=event,
        logger=logger,
        mod=kv.get("mod", ""),
        own=kv.get("own", "").lower() == "true",
        service=kv.get("service", ""),
        request_id=_s(kv.get("request_id")),
        channel=_s(kv.get("channel") or kv.get("channel_id")),
        code=_s(kv.get("code")),
        extra={k: v for k, v in kv.items() if k not in _CONSOLE_KNOWN},
        raw=raw,
    )


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

    console = _parse_console(body, line.stream, ts, raw)
    if console is not None:
        return console

    return LogRecordOut(
        stream=line.stream,
        ts=ts,
        level=_guess_level(body),
        source="raw",
        message=body,
        raw=raw,
    )


def _to_records(
    lines: list[LogLine],
    *,
    level: str = "ALL",
    q: str | None = None,
    name_map: Mapping[str, str] | None = None,
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
        # Resolve before the search filter so searching a login also matches
        # lines that only carry the numeric id.
        if name_map and rec.channel and rec.channel.isdigit():
            rec.channel_name = name_map.get(rec.channel)
        if needle and not (
            needle in rec.message.lower()
            or needle in rec.raw.lower()
            or (rec.channel_name and needle in rec.channel_name.lower())
        ):
            continue
        out.append(rec)
    return out


async def _channel_name_map() -> Mapping[str, str]:
    """Best-effort ``channel_id -> login`` for resolving log lines.

    Never raises and never gates the response: reading logs *because the DB
    is down* is this endpoint's most important use case, so a missing map
    just means the viewer falls back to showing the raw numeric id. (This is
    also why the pool isn't taken via ``Depends(get_db_pool)`` — that
    dependency 503s when the DB is unavailable.)
    """
    try:
        db_manager = get_database_manager()
        if not db_manager.is_connected:
            return {}
        return await ChannelRepository(db_manager.pool).get_channel_name_map()
    except Exception as e:
        LOGGER.debug("Channel name resolution unavailable: %s", e)
        return {}


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
        records=_to_records(lines, level=level, q=q, name_map=await _channel_name_map()),
    )
