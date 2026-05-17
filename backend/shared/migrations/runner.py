"""Lightweight migration runner with tracking table."""

from __future__ import annotations

import logging
from pathlib import Path

import asyncpg

LOGGER: logging.Logger = logging.getLogger(__name__)

# Default directory for migration SQL files
VERSIONS_DIR = Path(__file__).resolve().parent / "versions"

# Mapping of old → new version stems resulting from renumbering (Mar 2026).
# Applied as a preflight step so existing DBs stay in sync after file renames.
_VERSION_RENAMES: dict[str, str] = {
    "049_video_queue_add_bilibili": "050_video_queue_add_bilibili",
    "050_backfill_viewer_attendance_streaks": "051_backfill_viewer_attendance_streaks",
    "051_add_total_gifts_given": "052_add_total_gifts_given",
    "052_add_resub_gift_sub_event_types": "053_add_resub_gift_sub_event_types",
    "053_add_best_streak": "054_add_best_streak",
    "054_add_crosshairs": "055_add_crosshairs",
    "055_add_activation_codes": "056_add_activation_codes",
    "056_add_activation_requests": "057_add_activation_requests",
    "057_add_crosshair_copy_count": "058_add_crosshair_copy_count",
    "058_add_channel_display_name": "059_add_channel_display_name",
    "059_activation_codes_add_plain": "060_activation_codes_add_plain",
    "060_add_ai_settings": "061_add_ai_settings",
    "060_tokens_add_type": "062_tokens_add_type",
    "061_alter_ai_settings": "063_alter_ai_settings",
    "062_add_stream_events_channel_user_index": "064_add_stream_events_channel_user_index",
}


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

    async def apply_version_renames(self) -> None:
        """Rename old version stems in the tracking table after file renames.

        Safe to call on fresh DBs (no matching rows → no-op) and on DBs that
        already applied the old names (rows are updated in place).
        """
        await self.ensure_table()
        old_versions = list(_VERSION_RENAMES.keys())
        new_versions = list(_VERSION_RENAMES.values())
        async with self.pool.acquire() as conn:
            await conn.execute(
                f"""
                UPDATE {self.TRACKING_TABLE} AS t
                SET version = r.new_ver,
                    name    = r.new_ver || '.sql'
                FROM (
                    SELECT unnest($1::text[]) AS old_ver,
                           unnest($2::text[]) AS new_ver
                ) AS r
                WHERE t.version = r.old_ver
                  AND NOT EXISTS (
                      SELECT 1 FROM {self.TRACKING_TABLE} WHERE version = r.new_ver
                  )
                """,
                old_versions,
                new_versions,
            )

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
            LOGGER.info("No migration files found in %s", migrations_dir)
            return []

        newly_applied: list[str] = []
        for sql_path in sql_files:
            version = sql_path.stem  # e.g. "000_initial_schema"
            if version in applied:
                LOGGER.debug("Migration %s already applied, skipping", version)
                continue

            sql = sql_path.read_text(encoding="utf-8")
            await self._apply_one(version, sql_path.name, sql)
            newly_applied.append(version)

        if newly_applied:
            LOGGER.info(
                "Applied %d migration(s): %s",
                len(newly_applied),
                ", ".join(newly_applied),
            )
        else:
            LOGGER.info("Database is up to date — no pending migrations")

        return newly_applied

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _apply_one(self, version: str, name: str, sql: str) -> None:
        """Execute a single migration inside a transaction."""
        LOGGER.info("Applying migration: %s", version)
        try:
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
        except Exception:
            LOGGER.exception("Migration %s failed — transaction rolled back", version)
            raise
        LOGGER.info("Migration %s applied successfully", version)
