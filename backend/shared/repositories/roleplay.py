"""Tenant-scoped persistence for Canon Role-play drafts and revisions."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Final
from uuid import UUID

import asyncpg

from shared.models.roleplay import RoleplayImportResult, RoleplayRevision, RoleplaySet
from shared.repositories.ai_settings import AISettingsRepository
from shared.roleplay import (
    CompiledRoleplay,
    RoleplayPackage,
    compile_roleplay_package,
    decode_roleplay_package,
    encode_roleplay_package,
)

MAX_ROLEPLAY_SETS_PER_CHANNEL: Final = 5

_SET_SELECT = """
    SELECT roleplay_set.id,
           roleplay_set.channel_id,
           roleplay_set.name,
           roleplay_set.draft,
           roleplay_set.draft_version,
           roleplay_set.published_revision_id,
           roleplay_set.archived_at,
           roleplay_set.created_at,
           roleplay_set.updated_at,
           revision.id AS revision_id,
           revision.revision_number,
           revision.schema_version AS revision_schema_version,
           revision.compiler_version,
           revision.source_snapshot,
           revision.capsule,
           revision.compact_capsule,
           revision.content_digest,
           revision.published_at
    FROM roleplay_sets roleplay_set
    LEFT JOIN roleplay_revisions revision
      ON revision.channel_id = roleplay_set.channel_id
     AND revision.roleplay_set_id = roleplay_set.id
     AND revision.id = roleplay_set.published_revision_id
"""

_REVISION_COLUMNS = """
    id, channel_id, roleplay_set_id, revision_number, schema_version,
    compiler_version, source_snapshot, capsule, compact_capsule,
    content_digest, published_at
"""

_QUALIFIED_REVISION_COLUMNS = """
    revision.id,
    revision.channel_id,
    revision.roleplay_set_id,
    revision.revision_number,
    revision.schema_version,
    revision.compiler_version,
    revision.source_snapshot,
    revision.capsule,
    revision.compact_capsule,
    revision.content_digest,
    revision.published_at
"""


class RoleplayPersistenceError(ValueError):
    """Base class for stable application-facing persistence conflicts."""


class RoleplaySetNotFoundError(RoleplayPersistenceError):
    pass


class RoleplaySetLimitError(RoleplayPersistenceError):
    pass


class RoleplayDraftVersionConflictError(RoleplayPersistenceError):
    pass


class RoleplaySetArchivedError(RoleplayPersistenceError):
    pass


class RoleplayRevisionOwnershipError(RoleplayPersistenceError):
    pass


class RoleplayActiveSetError(RoleplayPersistenceError):
    pass


def _revision_from_row(row: asyncpg.Record | dict[str, Any]) -> RoleplayRevision:
    package = decode_roleplay_package(row["source_snapshot"])
    return RoleplayRevision(
        id=int(row["id"]),
        channel_id=str(row["channel_id"]),
        roleplay_set_id=row["roleplay_set_id"],
        revision_number=int(row["revision_number"]),
        package=package,
        compiled=CompiledRoleplay(
            schema_version=int(row["schema_version"]),
            compiler_version=int(row["compiler_version"]),
            capsule=str(row["capsule"]),
            compact_capsule=str(row["compact_capsule"]),
            content_digest=str(row["content_digest"]),
        ),
        published_at=row["published_at"],
    )


def _published_from_set_row(
    row: asyncpg.Record | dict[str, Any],
) -> RoleplayRevision | None:
    if row["published_revision_id"] is None:
        return None
    package = decode_roleplay_package(row["source_snapshot"])
    return RoleplayRevision(
        id=int(row["revision_id"]),
        channel_id=str(row["channel_id"]),
        roleplay_set_id=row["id"],
        revision_number=int(row["revision_number"]),
        package=package,
        compiled=CompiledRoleplay(
            schema_version=int(row["revision_schema_version"]),
            compiler_version=int(row["compiler_version"]),
            capsule=str(row["capsule"]),
            compact_capsule=str(row["compact_capsule"]),
            content_digest=str(row["content_digest"]),
        ),
        published_at=row["published_at"],
    )


def _set_from_row(row: asyncpg.Record | dict[str, Any]) -> RoleplaySet:
    return RoleplaySet(
        id=row["id"],
        channel_id=str(row["channel_id"]),
        name=str(row["name"]),
        draft=decode_roleplay_package(row["draft"]),
        draft_version=int(row["draft_version"]),
        published=_published_from_set_row(row),
        archived_at=row["archived_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _validate_name(name: str) -> str:
    normalized = name.strip()
    if not 1 <= len(normalized) <= 100:
        raise ValueError("role-play set name must contain between 1 and 100 characters")
    return normalized


class RoleplayRepository:
    """Publish immutable revisions while keeping mutable drafts tenant-owned."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def list_sets(
        self, channel_id: str, *, include_archived: bool = False
    ) -> tuple[RoleplaySet, ...]:
        archived_filter = "" if include_archived else "AND roleplay_set.archived_at IS NULL"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                {_SET_SELECT}
                WHERE roleplay_set.channel_id = $1
                  {archived_filter}
                ORDER BY roleplay_set.created_at ASC, roleplay_set.id ASC
                """,
                channel_id,
            )
        return tuple(_set_from_row(row) for row in rows)

    async def get_set(self, channel_id: str, roleplay_set_id: UUID) -> RoleplaySet | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                {_SET_SELECT}
                WHERE roleplay_set.channel_id = $1
                  AND roleplay_set.id = $2
                """,
                channel_id,
                roleplay_set_id,
            )
        return _set_from_row(row) if row is not None else None

    async def get_revision(
        self,
        channel_id: str,
        roleplay_set_id: UUID,
        revision_id: int,
    ) -> RoleplayRevision | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {_QUALIFIED_REVISION_COLUMNS}
                FROM roleplay_revisions revision
                WHERE revision.channel_id = $1
                  AND revision.roleplay_set_id = $2
                  AND revision.id = $3
                """,
                channel_id,
                roleplay_set_id,
                revision_id,
            )
        return _revision_from_row(row) if row is not None else None

    async def create_set(
        self,
        channel_id: str,
        name: str,
        draft: RoleplayPackage,
    ) -> RoleplaySet:
        normalized_name = _validate_name(name)
        document = encode_roleplay_package(draft)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                channel = await conn.fetchval(
                    "SELECT channel_id FROM channels WHERE channel_id = $1 FOR UPDATE",
                    channel_id,
                )
                if channel is None:
                    raise RoleplaySetNotFoundError("channel was not found")
                active_count = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM roleplay_sets
                    WHERE channel_id = $1
                      AND archived_at IS NULL
                    """,
                    channel_id,
                )
                if int(active_count) >= MAX_ROLEPLAY_SETS_PER_CHANNEL:
                    raise RoleplaySetLimitError("channel role-play set limit reached")
                row = await conn.fetchrow(
                    """
                    INSERT INTO roleplay_sets (channel_id, name, draft)
                    VALUES ($1, $2, $3)
                    RETURNING id, channel_id, name, draft, draft_version,
                              published_revision_id, archived_at, created_at, updated_at
                    """,
                    channel_id,
                    normalized_name,
                    document,
                )
        if row is None:
            raise RuntimeError("failed to create role-play set")
        return _set_from_row(row)

    async def update_draft(
        self,
        channel_id: str,
        roleplay_set_id: UUID,
        draft: RoleplayPackage,
        *,
        expected_draft_version: int,
        name: str | None = None,
    ) -> RoleplaySet:
        if expected_draft_version <= 0:
            raise ValueError("expected_draft_version must be positive")
        document = encode_roleplay_package(draft)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                current = await self._lock_set(conn, channel_id, roleplay_set_id)
                self._require_editable_version(current, expected_draft_version)
                next_name = current.name if name is None else _validate_name(name)
                row = await conn.fetchrow(
                    """
                    UPDATE roleplay_sets
                    SET name = $3,
                        draft = $4,
                        draft_version = draft_version + 1
                    WHERE channel_id = $1
                      AND id = $2
                    RETURNING draft_version, updated_at
                    """,
                    channel_id,
                    roleplay_set_id,
                    next_name,
                    document,
                )
        if row is None:
            raise RuntimeError("failed to update role-play draft")
        return replace(
            current,
            name=next_name,
            draft=draft,
            draft_version=int(row["draft_version"]),
            updated_at=row["updated_at"],
        )

    async def publish(
        self,
        channel_id: str,
        roleplay_set_id: UUID,
        *,
        expected_draft_version: int,
    ) -> RoleplayRevision:
        if expected_draft_version <= 0:
            raise ValueError("expected_draft_version must be positive")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                current = await self._lock_set(conn, channel_id, roleplay_set_id)
                self._require_editable_version(current, expected_draft_version)
                compiled = compile_roleplay_package(current.draft)
                if self._matches_compiled(current.published, compiled):
                    assert current.published is not None
                    return current.published

                row = await conn.fetchrow(
                    f"""
                    INSERT INTO roleplay_revisions
                        (channel_id, roleplay_set_id, revision_number,
                         schema_version, compiler_version, source_snapshot,
                         capsule, compact_capsule, content_digest)
                    SELECT $1,
                           $2,
                           COALESCE(MAX(revision_number), 0) + 1,
                           $3,
                           $4,
                           $5,
                           $6,
                           $7,
                           $8
                    FROM roleplay_revisions
                    WHERE channel_id = $1
                      AND roleplay_set_id = $2
                    RETURNING {_REVISION_COLUMNS}
                    """,
                    channel_id,
                    roleplay_set_id,
                    compiled.schema_version,
                    compiled.compiler_version,
                    encode_roleplay_package(current.draft),
                    compiled.capsule,
                    compiled.compact_capsule,
                    compiled.content_digest,
                )
                if row is None:
                    raise RuntimeError("failed to publish role-play revision")
                revision = _revision_from_row(row)
                await conn.execute(
                    """
                    UPDATE roleplay_sets
                    SET published_revision_id = $3
                    WHERE channel_id = $1
                      AND id = $2
                    """,
                    channel_id,
                    roleplay_set_id,
                    revision.id,
                )
        return revision

    async def activate(
        self,
        channel_id: str,
        roleplay_set_id: UUID,
        revision_id: int,
    ) -> RoleplayRevision:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    f"""
                    SELECT {_QUALIFIED_REVISION_COLUMNS}
                    FROM roleplay_revisions revision
                    JOIN roleplay_sets roleplay_set
                      ON roleplay_set.channel_id = revision.channel_id
                     AND roleplay_set.id = revision.roleplay_set_id
                    WHERE revision.channel_id = $1
                      AND revision.roleplay_set_id = $2
                      AND revision.id = $3
                      AND roleplay_set.archived_at IS NULL
                    FOR UPDATE OF roleplay_set
                    """,
                    channel_id,
                    roleplay_set_id,
                    revision_id,
                )
                if row is None:
                    raise RoleplayRevisionOwnershipError(
                        "role-play revision is unavailable for this channel"
                    )
                revision = _revision_from_row(row)
                await conn.execute(
                    """
                    INSERT INTO ai_settings (channel_id)
                    VALUES ($1)
                    ON CONFLICT (channel_id) DO NOTHING
                    """,
                    channel_id,
                )
                await conn.execute(
                    """
                    UPDATE ai_settings
                    SET assistant_mode = 'roleplay',
                        active_roleplay_revision_id = $2,
                        updated_at = NOW()
                    WHERE channel_id = $1
                    """,
                    channel_id,
                    revision_id,
                )
        AISettingsRepository(self.pool).invalidate_cache(channel_id)
        return revision

    async def import_and_activate(
        self,
        channel_id: str,
        name: str,
        package: RoleplayPackage,
    ) -> RoleplayImportResult:
        """Install and activate a verified snapshot in one tenant transaction."""

        normalized_name = _validate_name(name)
        document = encode_roleplay_package(package)
        compiled = compile_roleplay_package(package)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                channel = await conn.fetchval(
                    "SELECT channel_id FROM channels WHERE channel_id = $1 FOR UPDATE",
                    channel_id,
                )
                if channel is None:
                    raise RoleplaySetNotFoundError("channel was not found")

                matching_row = await conn.fetchrow(
                    f"""
                    {_SET_SELECT}
                    WHERE roleplay_set.channel_id = $1
                      AND roleplay_set.archived_at IS NULL
                      AND revision.content_digest = $2
                    ORDER BY roleplay_set.created_at ASC, roleplay_set.id ASC
                    LIMIT 1
                    FOR UPDATE OF roleplay_set
                    """,
                    channel_id,
                    compiled.content_digest,
                )
                if matching_row is not None:
                    roleplay_set = _set_from_row(matching_row)
                    if roleplay_set.published is None:  # pragma: no cover - SQL invariant
                        raise RuntimeError("matching role-play set has no published revision")
                    revision = roleplay_set.published
                    reused = True
                else:
                    active_count = await conn.fetchval(
                        """
                        SELECT COUNT(*)
                        FROM roleplay_sets
                        WHERE channel_id = $1
                          AND archived_at IS NULL
                        """,
                        channel_id,
                    )
                    if int(active_count) >= MAX_ROLEPLAY_SETS_PER_CHANNEL:
                        raise RoleplaySetLimitError("channel role-play set limit reached")
                    set_row = await conn.fetchrow(
                        """
                        INSERT INTO roleplay_sets (channel_id, name, draft)
                        VALUES ($1, $2, $3)
                        RETURNING id, channel_id, name, draft, draft_version,
                                  published_revision_id, archived_at, created_at, updated_at
                        """,
                        channel_id,
                        normalized_name,
                        document,
                    )
                    if set_row is None:  # pragma: no cover - INSERT RETURNING invariant
                        raise RuntimeError("failed to import role-play set")
                    roleplay_set = _set_from_row(set_row)
                    revision_row = await conn.fetchrow(
                        f"""
                        INSERT INTO roleplay_revisions
                            (channel_id, roleplay_set_id, revision_number,
                             schema_version, compiler_version, source_snapshot,
                             capsule, compact_capsule, content_digest)
                        VALUES ($1, $2, 1, $3, $4, $5, $6, $7, $8)
                        RETURNING {_REVISION_COLUMNS}
                        """,
                        channel_id,
                        roleplay_set.id,
                        compiled.schema_version,
                        compiled.compiler_version,
                        document,
                        compiled.capsule,
                        compiled.compact_capsule,
                        compiled.content_digest,
                    )
                    if revision_row is None:  # pragma: no cover - INSERT RETURNING invariant
                        raise RuntimeError("failed to import role-play revision")
                    revision = _revision_from_row(revision_row)
                    pointer_row = await conn.fetchrow(
                        """
                        UPDATE roleplay_sets
                        SET published_revision_id = $3
                        WHERE channel_id = $1
                          AND id = $2
                        RETURNING updated_at
                        """,
                        channel_id,
                        roleplay_set.id,
                        revision.id,
                    )
                    if pointer_row is None:  # pragma: no cover - locked row invariant
                        raise RuntimeError("failed to publish imported role-play set")
                    roleplay_set = replace(
                        roleplay_set,
                        published=revision,
                        updated_at=pointer_row["updated_at"],
                    )
                    reused = False

                await conn.execute(
                    """
                    INSERT INTO ai_settings
                        (channel_id, assistant_mode, active_roleplay_revision_id)
                    VALUES ($1, 'roleplay', $2)
                    ON CONFLICT (channel_id) DO UPDATE SET
                        assistant_mode = 'roleplay',
                        active_roleplay_revision_id = EXCLUDED.active_roleplay_revision_id,
                        updated_at = NOW()
                    """,
                    channel_id,
                    revision.id,
                )
        AISettingsRepository(self.pool).invalidate_cache(channel_id)
        return RoleplayImportResult(
            roleplay_set=roleplay_set,
            revision=revision,
            reused=reused,
        )

    async def use_persona(self, channel_id: str) -> None:
        """Switch modes atomically without deleting either mode's authoring data."""

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ai_settings
                    (channel_id, assistant_mode, active_roleplay_revision_id)
                VALUES ($1, 'persona', NULL)
                ON CONFLICT (channel_id) DO UPDATE SET
                    assistant_mode = 'persona',
                    active_roleplay_revision_id = NULL,
                    updated_at = NOW()
                """,
                channel_id,
            )
        AISettingsRepository(self.pool).invalidate_cache(channel_id)

    async def archive(self, channel_id: str, roleplay_set_id: UUID) -> RoleplaySet:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                current = await self._lock_set(conn, channel_id, roleplay_set_id)
                if current.is_archived:
                    return current
                is_active = await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM ai_settings settings
                        JOIN roleplay_revisions revision
                          ON revision.channel_id = settings.channel_id
                         AND revision.id = settings.active_roleplay_revision_id
                        WHERE settings.channel_id = $1
                          AND settings.assistant_mode = 'roleplay'
                          AND revision.roleplay_set_id = $2
                    )
                    """,
                    channel_id,
                    roleplay_set_id,
                )
                if is_active:
                    raise RoleplayActiveSetError(
                        "switch away from the active role-play set before archiving"
                    )
                row = await conn.fetchrow(
                    """
                    UPDATE roleplay_sets
                    SET archived_at = NOW()
                    WHERE channel_id = $1
                      AND id = $2
                    RETURNING archived_at, updated_at
                    """,
                    channel_id,
                    roleplay_set_id,
                )
        if row is None:
            raise RuntimeError("failed to archive role-play set")
        return replace(
            current,
            archived_at=row["archived_at"],
            updated_at=row["updated_at"],
        )

    async def get_active_revision(self, channel_id: str) -> RoleplayRevision | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {_QUALIFIED_REVISION_COLUMNS}
                FROM ai_settings settings
                JOIN roleplay_revisions revision
                  ON revision.channel_id = settings.channel_id
                 AND revision.id = settings.active_roleplay_revision_id
                JOIN roleplay_sets roleplay_set
                  ON roleplay_set.channel_id = revision.channel_id
                 AND roleplay_set.id = revision.roleplay_set_id
                WHERE settings.channel_id = $1
                  AND settings.assistant_mode = 'roleplay'
                  AND roleplay_set.archived_at IS NULL
                """,
                channel_id,
            )
        return _revision_from_row(row) if row is not None else None

    async def _lock_set(
        self,
        conn: asyncpg.Connection,
        channel_id: str,
        roleplay_set_id: UUID,
    ) -> RoleplaySet:
        row = await conn.fetchrow(
            f"""
            {_SET_SELECT}
            WHERE roleplay_set.channel_id = $1
              AND roleplay_set.id = $2
            FOR UPDATE OF roleplay_set
            """,
            channel_id,
            roleplay_set_id,
        )
        if row is None:
            raise RoleplaySetNotFoundError("role-play set was not found")
        return _set_from_row(row)

    @staticmethod
    def _require_editable_version(current: RoleplaySet, expected_version: int) -> None:
        if current.is_archived:
            raise RoleplaySetArchivedError("archived role-play sets cannot be changed")
        if current.draft_version != expected_version:
            raise RoleplayDraftVersionConflictError("role-play draft version is stale")

    @staticmethod
    def _matches_compiled(
        published: RoleplayRevision | None,
        compiled: CompiledRoleplay,
    ) -> bool:
        return published is not None and published.compiled == compiled
