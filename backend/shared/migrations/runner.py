"""Lightweight migration runner with tracking table."""

from __future__ import annotations

import logging
from pathlib import Path

import asyncpg

logger = logging.getLogger(__name__)

# Default directory for migration SQL files
VERSIONS_DIR = Path(__file__).resolve().parent / "versions"


class MigrationRunner:
    """Execute and track database migrations.

    Migrations are plain SQL files stored in ``versions/`` with the naming
    convention ``NNN_description.sql`` where *NNN* is a zero-padded version
    number.  Applied versions are recorded in the ``schema_migrations`` table
    so they are never re-applied.
    """

    TRACKING_TABLE = "schema_migrations"

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ensure_table(self) -> None:
        """Create the tracking table if it does not exist."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.TRACKING_TABLE} (
                    version  TEXT PRIMARY KEY,
                    name     TEXT NOT NULL,
                    applied_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )

    async def get_applied(self) -> set[str]:
        """Return the set of already-applied migration versions."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT version FROM {self.TRACKING_TABLE}"  # noqa: S608
            )
            return {row["version"] for row in rows}

    async def run_pending(
        self,
        migrations_dir: Path | None = None,
    ) -> list[str]:
        """Discover and apply all pending migrations in order.

        Returns the list of newly-applied version strings.
        """
        migrations_dir = migrations_dir or VERSIONS_DIR
        await self.ensure_table()
        applied = await self.get_applied()

        # Discover SQL files sorted by filename (NNN_ prefix ensures order)
        sql_files = sorted(migrations_dir.glob("*.sql"))
        if not sql_files:
            logger.info("No migration files found in %s", migrations_dir)
            return []

        newly_applied: list[str] = []
        for sql_path in sql_files:
            version = sql_path.stem  # e.g. "000_initial_schema"
            if version in applied:
                logger.debug("Migration %s already applied, skipping", version)
                continue

            sql = sql_path.read_text(encoding="utf-8")
            await self._apply_one(version, sql_path.name, sql)
            newly_applied.append(version)

        if newly_applied:
            logger.info(
                "Applied %d migration(s): %s",
                len(newly_applied),
                ", ".join(newly_applied),
            )
        else:
            logger.info("Database is up to date — no pending migrations")

        return newly_applied

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _apply_one(self, version: str, name: str, sql: str) -> None:
        """Execute a single migration inside a transaction."""
        logger.info("Applying migration: %s", version)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    f"""
                    INSERT INTO {self.TRACKING_TABLE} (version, name)
                    VALUES ($1, $2)
                    """,
                    version,
                    name,
                )
        logger.info("Migration %s applied successfully", version)
