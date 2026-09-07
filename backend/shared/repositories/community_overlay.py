"""Durable cursor delivery and public-key management for community overlays."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from shared.community_overlay_blocks import get_community_overlay_block
from shared.community_overlay_themes import (
    CommunityOverlayThemeVersionConflictError,
)
from shared.models.attendance import (
    CommunityOverlayAccess,
    CommunityOverlayEvent,
    CommunityOverlayFeed,
    CommunityOverlayThemePublished,
    CommunityOverlayThemeState,
)

_ACCESS_COLUMNS = "channel_id, public_key, enabled, created_at, updated_at"
_EVENT_COLUMNS = (
    "id, channel_id, event_type, schema_version, source, actor_user_id, "
    "actor_display_name, payload, occurred_at, expires_at"
)
LOGGER: logging.Logger = logging.getLogger(__name__)
_THEME_STATE_SELECT = """
    SELECT profile.channel_id,
           profile.block_type,
           profile.renderer,
           profile.schema_version,
           profile.draft_theme,
           profile.draft_version,
           profile.published_revision_id,
           revision.renderer AS published_renderer,
           revision.schema_version AS published_schema_version,
           revision.theme AS published_theme,
           revision.created_at AS published_created_at,
           profile.updated_at
    FROM community_overlay_profiles profile
    LEFT JOIN community_overlay_revisions revision
      ON revision.channel_id = profile.channel_id
     AND revision.block_type = profile.block_type
     AND revision.id = profile.published_revision_id
    WHERE profile.channel_id = $1
      AND profile.block_type = $2
"""


def _to_access(row: asyncpg.Record) -> CommunityOverlayAccess:
    return CommunityOverlayAccess(
        channel_id=row["channel_id"],
        public_key=row["public_key"],
        enabled=row["enabled"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_published_theme(row: asyncpg.Record, block_type: str) -> CommunityOverlayThemePublished:
    definition = get_community_overlay_block(block_type)
    return CommunityOverlayThemePublished(
        revision_id=row["published_revision_id"],
        renderer=row["published_renderer"],
        schema_version=row["published_schema_version"],
        theme=definition.validate_theme(row["published_theme"]),
        created_at=row["published_created_at"],
    )


def _to_theme_state(row: asyncpg.Record) -> CommunityOverlayThemeState:
    definition = get_community_overlay_block(row["block_type"])
    return CommunityOverlayThemeState(
        channel_id=row["channel_id"],
        block_type=row["block_type"],
        renderer=row["renderer"],
        schema_version=row["schema_version"],
        draft_theme=definition.validate_theme(row["draft_theme"]),
        published=_to_published_theme(row, row["block_type"]),
        updated_at=row["updated_at"],
        draft_version=row["draft_version"],
    )


class CommunityOverlayRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def resolve_public_channel(self, public_key: UUID) -> str | None:
        """Resolve an enabled capability without returning or logging the key."""
        async with self.pool.acquire() as conn:
            channel_id = await conn.fetchval(
                "SELECT channel_id FROM community_overlay_channels "
                "WHERE public_key = $1 AND enabled = TRUE",
                public_key,
            )
        return str(channel_id) if channel_id is not None else None

    async def get_or_create_channel(self, channel_id: str) -> CommunityOverlayAccess:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO community_overlay_channels (channel_id) VALUES ($1) "
                    "ON CONFLICT (channel_id) DO NOTHING",
                    channel_id,
                )
                row = await conn.fetchrow(
                    f"SELECT {_ACCESS_COLUMNS} FROM community_overlay_channels "
                    "WHERE channel_id = $1",
                    channel_id,
                )
        if row is None:
            raise ValueError(f"Failed to load overlay access for channel {channel_id}")
        return _to_access(row)

    async def rotate_public_key(self, channel_id: str) -> CommunityOverlayAccess:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO community_overlay_channels (channel_id) VALUES ($1) "
                    "ON CONFLICT (channel_id) DO NOTHING",
                    channel_id,
                )
                row = await conn.fetchrow(
                    f"""
                    UPDATE community_overlay_channels
                    SET public_key = gen_random_uuid()
                    WHERE channel_id = $1
                    RETURNING {_ACCESS_COLUMNS}
                    """,
                    channel_id,
                )
        if row is None:
            raise ValueError(f"Failed to rotate overlay key for channel {channel_id}")
        return _to_access(row)

    async def set_enabled(self, channel_id: str, enabled: bool) -> CommunityOverlayAccess:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO community_overlay_channels (channel_id) VALUES ($1) "
                    "ON CONFLICT (channel_id) DO NOTHING",
                    channel_id,
                )
                row = await conn.fetchrow(
                    f"""
                    UPDATE community_overlay_channels
                    SET enabled = $2
                    WHERE channel_id = $1
                    RETURNING {_ACCESS_COLUMNS}
                    """,
                    channel_id,
                    enabled,
                )
        if row is None:
            raise ValueError(f"Failed to update overlay access for channel {channel_id}")
        return _to_access(row)

    async def _lock_theme_state(
        self, conn: asyncpg.Connection, channel_id: str, block_type: str
    ) -> CommunityOverlayThemeState:
        definition = get_community_overlay_block(block_type)
        await conn.execute(
            """
            INSERT INTO community_overlay_profiles
                (channel_id, block_type, renderer, schema_version, draft_theme)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (channel_id, block_type) DO NOTHING
            """,
            channel_id,
            block_type,
            definition.renderer,
            definition.schema_version,
            dict(definition.default_theme),
        )
        row = await conn.fetchrow(
            f"{_THEME_STATE_SELECT} FOR UPDATE OF profile", channel_id, block_type
        )
        if row is None:
            raise ValueError(f"Failed to load overlay theme for channel {channel_id}")

        if row["published_revision_id"] is None:
            revision_id = await conn.fetchval(
                """
                INSERT INTO community_overlay_revisions
                    (channel_id, block_type, revision_number, renderer, schema_version, theme)
                SELECT profile.channel_id,
                       profile.block_type,
                       COALESCE(MAX(revision.revision_number), 0) + 1,
                       profile.renderer,
                       profile.schema_version,
                       $3
                FROM community_overlay_profiles profile
                LEFT JOIN community_overlay_revisions revision
                  ON revision.channel_id = profile.channel_id
                 AND revision.block_type = profile.block_type
                WHERE profile.channel_id = $1
                  AND profile.block_type = $2
                GROUP BY profile.channel_id, profile.block_type, profile.renderer,
                         profile.schema_version
                RETURNING id
                """,
                channel_id,
                block_type,
                dict(definition.default_theme),
            )
            if revision_id is None:
                raise RuntimeError("Failed to create initial overlay theme revision")
            await conn.execute(
                """
                UPDATE community_overlay_profiles
                SET published_revision_id = $3
                WHERE channel_id = $1
                  AND block_type = $2
                """,
                channel_id,
                block_type,
                revision_id,
            )
            row = await conn.fetchrow(_THEME_STATE_SELECT, channel_id, block_type)
            if row is None:
                raise RuntimeError("Failed to reload initial overlay theme revision")

        return _to_theme_state(row)

    async def get_theme_state(self, channel_id: str, block_type: str) -> CommunityOverlayThemeState:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                return await self._lock_theme_state(conn, channel_id, block_type)

    async def update_theme_draft(
        self,
        channel_id: str,
        block_type: str,
        theme: dict[str, object],
        expected_draft_version: int,
    ) -> CommunityOverlayThemeState:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                current = await self._lock_theme_state(conn, channel_id, block_type)
                if current.draft_version != expected_draft_version:
                    raise CommunityOverlayThemeVersionConflictError()
                row = await conn.fetchrow(
                    """
                    WITH updated AS (
                        UPDATE community_overlay_profiles
                        SET draft_theme = $3,
                            draft_version = draft_version + 1
                        WHERE channel_id = $1
                          AND block_type = $2
                        RETURNING channel_id, block_type, renderer, schema_version, draft_theme, draft_version,
                                  published_revision_id, updated_at
                    )
                    SELECT updated.channel_id,
                           updated.block_type,
                           updated.renderer,
                           updated.schema_version,
                           updated.draft_theme,
                           updated.draft_version,
                           updated.published_revision_id,
                           revision.renderer AS published_renderer,
                           revision.schema_version AS published_schema_version,
                           revision.theme AS published_theme,
                           revision.created_at AS published_created_at,
                           updated.updated_at
                    FROM updated
                    JOIN community_overlay_revisions revision
                      ON revision.channel_id = updated.channel_id
                     AND revision.block_type = updated.block_type
                     AND revision.id = updated.published_revision_id
                    """,
                    channel_id,
                    block_type,
                    theme,
                )
        if row is None:
            raise RuntimeError("Failed to update overlay theme draft")
        return _to_theme_state(row)

    async def publish_theme(
        self, channel_id: str, block_type: str, expected_draft_version: int
    ) -> CommunityOverlayThemeState:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                current = await self._lock_theme_state(conn, channel_id, block_type)
                if current.draft_version != expected_draft_version:
                    raise CommunityOverlayThemeVersionConflictError()
                if not current.has_unpublished_changes:
                    return current

                revision_id = await conn.fetchval(
                    """
                    INSERT INTO community_overlay_revisions
                        (channel_id, block_type, revision_number, renderer, schema_version, theme)
                    SELECT profile.channel_id,
                           profile.block_type,
                           COALESCE(MAX(revision.revision_number), 0) + 1,
                           profile.renderer,
                           profile.schema_version,
                           $3
                    FROM community_overlay_profiles profile
                    LEFT JOIN community_overlay_revisions revision
                      ON revision.channel_id = profile.channel_id
                     AND revision.block_type = profile.block_type
                    WHERE profile.channel_id = $1
                      AND profile.block_type = $2
                    GROUP BY profile.channel_id, profile.block_type, profile.renderer,
                             profile.schema_version
                    RETURNING id
                    """,
                    channel_id,
                    block_type,
                    current.draft_theme,
                )
                if revision_id is None:
                    raise RuntimeError("Failed to publish overlay theme revision")
                await conn.execute(
                    """
                    UPDATE community_overlay_profiles
                    SET published_revision_id = $3
                    WHERE channel_id = $1
                      AND block_type = $2
                    """,
                    channel_id,
                    block_type,
                    revision_id,
                )
                row = await conn.fetchrow(_THEME_STATE_SELECT, channel_id, block_type)
        if row is None:
            raise RuntimeError("Failed to reload published overlay theme")
        return _to_theme_state(row)

    async def reset_theme_draft(
        self, channel_id: str, block_type: str, expected_draft_version: int
    ) -> CommunityOverlayThemeState:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                current = await self._lock_theme_state(conn, channel_id, block_type)
                if current.draft_version != expected_draft_version:
                    raise CommunityOverlayThemeVersionConflictError()
                if not current.has_unpublished_changes:
                    return current
                row = await conn.fetchrow(
                    """
                    WITH updated AS (
                        UPDATE community_overlay_profiles profile
                        SET draft_theme = revision.theme,
                            draft_version = profile.draft_version + 1
                        FROM community_overlay_revisions revision
                        WHERE profile.channel_id = $1
                          AND profile.block_type = $2
                          AND revision.channel_id = profile.channel_id
                          AND revision.block_type = profile.block_type
                          AND revision.id = profile.published_revision_id
                        RETURNING profile.channel_id, profile.block_type, profile.renderer, profile.schema_version,
                                  profile.draft_theme, profile.draft_version,
                                  profile.published_revision_id,
                                  profile.updated_at
                    )
                    SELECT updated.channel_id,
                           updated.block_type,
                           updated.renderer,
                           updated.schema_version,
                           updated.draft_theme,
                           updated.draft_version,
                           updated.published_revision_id,
                           revision.renderer AS published_renderer,
                           revision.schema_version AS published_schema_version,
                           revision.theme AS published_theme,
                           revision.created_at AS published_created_at,
                           updated.updated_at
                    FROM updated
                    JOIN community_overlay_revisions revision
                      ON revision.channel_id = updated.channel_id
                     AND revision.block_type = updated.block_type
                     AND revision.id = updated.published_revision_id
                    """,
                    channel_id,
                    block_type,
                )
        if row is None:
            raise RuntimeError("Failed to reset overlay theme draft")
        return _to_theme_state(row)

    async def get_public_theme(
        self, public_key: UUID, block_type: str
    ) -> CommunityOverlayThemePublished | None:
        definition = get_community_overlay_block(block_type)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT revision.id AS revision_id,
                       COALESCE(revision.renderer, $2) AS renderer,
                       COALESCE(revision.schema_version, $3) AS schema_version,
                       COALESCE(revision.theme, $4) AS theme,
                       revision.created_at
                FROM community_overlay_channels access
                LEFT JOIN community_overlay_profiles profile
                  ON profile.channel_id = access.channel_id
                 AND profile.block_type = $5
                LEFT JOIN community_overlay_revisions revision
                  ON revision.channel_id = profile.channel_id
                 AND revision.block_type = profile.block_type
                 AND revision.id = profile.published_revision_id
                WHERE access.public_key = $1
                  AND access.enabled = TRUE
                """,
                public_key,
                definition.renderer,
                definition.schema_version,
                dict(definition.default_theme),
                block_type,
            )
        if row is None:
            return None
        return CommunityOverlayThemePublished(
            revision_id=row["revision_id"],
            renderer=row["renderer"],
            schema_version=row["schema_version"],
            theme=definition.validate_theme(row["theme"]),
            created_at=row["created_at"],
        )

    async def publish_event(
        self,
        *,
        channel_id: str,
        event_type: str,
        schema_version: int,
        source: str,
        actor_user_id: str | None,
        actor_display_name: str | None,
        payload: dict[str, Any],
        occurred_at: datetime,
        expires_at: datetime | None,
        idempotency_key: str,
    ) -> int:
        async with self.pool.acquire() as conn:
            event_id = await conn.fetchval(
                """
                INSERT INTO community_overlay_events
                    (channel_id, event_type, schema_version, source, actor_user_id,
                     actor_display_name, payload, occurred_at, expires_at, idempotency_key)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (channel_id, idempotency_key) DO UPDATE SET
                    idempotency_key = EXCLUDED.idempotency_key
                RETURNING id
                """,
                channel_id,
                event_type,
                schema_version,
                source,
                actor_user_id,
                actor_display_name,
                payload,
                occurred_at,
                expires_at,
                idempotency_key,
            )
        if event_id is None:
            raise RuntimeError("Failed to publish community overlay event")
        return int(event_id)

    async def get_feed(
        self,
        public_key: UUID,
        *,
        after_id: int | None,
        limit: int,
        now: datetime,
    ) -> CommunityOverlayFeed | None:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if after_id is not None and after_id < 0:
            raise ValueError("after_id must be non-negative")

        async with self.pool.acquire() as conn:
            access = await conn.fetchrow(
                f"""
                SELECT access.{_ACCESS_COLUMNS},
                       COALESCE((
                           SELECT MAX(event.id)
                           FROM community_overlay_events event
                           WHERE event.channel_id = access.channel_id
                       ), 0) AS latest_id
                FROM community_overlay_channels access
                WHERE access.public_key = $1
                  AND access.enabled = TRUE
                """,
                public_key,
            )
            if access is None:
                return None

            latest_id = int(access["latest_id"])
            if after_id is None:
                return CommunityOverlayFeed(cursor=latest_id, events=())

            rows = await conn.fetch(
                f"""
                SELECT {_EVENT_COLUMNS}
                FROM community_overlay_events
                WHERE channel_id = $1
                  AND id > $2
                  AND (expires_at IS NULL OR expires_at > $3)
                ORDER BY id ASC
                LIMIT $4
                """,
                access["channel_id"],
                after_id,
                now,
                limit,
            )

        events = tuple(CommunityOverlayEvent(**dict(row)) for row in rows)
        cursor = events[-1].id if events else max(after_id, latest_id)
        return CommunityOverlayFeed(cursor=cursor, events=events)

    async def prune_expired(self, cutoff: datetime) -> int:
        """Delete visual events that can no longer be delivered."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM community_overlay_events "
                "WHERE expires_at IS NOT NULL AND expires_at <= $1",
                cutoff,
            )
        return int(result.split()[-1]) if result.startswith("DELETE") else 0


async def community_overlay_cleanup_loop(db_manager) -> None:
    """Prune expired visual events once a day without touching feature ledgers."""
    while True:
        try:
            await asyncio.sleep(86_400)
            if not db_manager.is_connected:
                continue
            removed = await CommunityOverlayRepository(db_manager.pool).prune_expired(
                datetime.now(UTC)
            )
            if removed:
                LOGGER.info("community_overlay_events_pruned", extra={"rows": removed})
        except asyncio.CancelledError:
            return
        except Exception:
            LOGGER.exception("community_overlay_events_prune_failed")
