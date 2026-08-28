"""Repository for the client_errors telemetry table (migration 085)."""

from __future__ import annotations

import logging
import random

import asyncpg

LOGGER = logging.getLogger(__name__)

# On this fraction of inserts, also trim the table to a hard row ceiling.
_TRIM_PROBABILITY = 1 / 200
_HARD_ROW_CEILING = 50_000
_RETENTION_DAYS = 14


class ClientErrorRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def insert(
        self,
        *,
        kind: str,
        fingerprint: str,
        message: str,
        url: str,
        stack: str | None = None,
        component_stack: str | None = None,
        route: str | None = None,
        request_id: str | None = None,
        error_code: str | None = None,
        http_status: int | None = None,
        user_id: str | None = None,
        user_agent: str | None = None,
        app_version: str | None = None,
        ip_hash: str | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO client_errors (
                    kind, fingerprint, message, stack, component_stack, url, route,
                    request_id, error_code, http_status, user_id, user_agent,
                    app_version, ip_hash
                )
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::uuid,$12,$13,$14)
                """,
                kind,
                fingerprint,
                message,
                stack,
                component_stack,
                url,
                route,
                request_id,
                error_code,
                http_status,
                user_id,
                user_agent,
                app_version,
                ip_hash,
            )
            if random.random() < _TRIM_PROBABILITY:
                await conn.execute(
                    """
                    DELETE FROM client_errors
                    WHERE id < (SELECT MAX(id) - $1 FROM client_errors)
                    """,
                    _HARD_ROW_CEILING,
                )

    async def prune_old(self) -> int:
        """Delete rows older than the retention window. Returns rows removed."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                f"DELETE FROM client_errors WHERE occurred_at < NOW() - INTERVAL '{_RETENTION_DAYS} days'"  # noqa: S608
            )
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0
