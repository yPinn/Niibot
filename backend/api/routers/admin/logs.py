"""Admin: Docker container log access (owner-only)."""

import logging
import struct

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
    ("nb-scrapling", "Scrapling"),
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

    return ContainerLogsResponse(container=container, lines=_parse_docker_stream(raw))
