"""Shared JSON fetch for the import source adapters.

Both platforms are read-only and best-effort: a failure means "we could not
read this list", which the caller turns into an empty section rather than an
error page. Returning None for every failure mode keeps that decision in one
place instead of spreading httpx handling through both adapters.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

LOGGER: logging.Logger = logging.getLogger(__name__)


async def get_json(
    http: httpx.AsyncClient,
    url: str,
    *,
    label: str,
    headers: dict[str, str] | None = None,
) -> Any | None:
    """GET *url* and parse JSON. Returns None on transport, status, or parse failure."""
    try:
        response = await http.get(url, headers=headers)
    except httpx.HTTPError as exc:
        LOGGER.warning("%s GET %s failed: %s", label, url, exc)
        return None
    if response.status_code != 200:
        LOGGER.warning("%s GET %s → %s", label, url, response.status_code)
        return None
    try:
        return response.json()
    except ValueError:
        LOGGER.warning("%s GET %s returned non-JSON", label, url)
        return None
