"""Typed persistence models for Canon Role-play drafts and revisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from shared.roleplay.contracts import CompiledRoleplay, RoleplayPackage


@dataclass(frozen=True, slots=True)
class RoleplayRevision:
    id: int
    channel_id: str
    roleplay_set_id: UUID
    revision_number: int
    package: RoleplayPackage
    compiled: CompiledRoleplay
    published_at: datetime


@dataclass(frozen=True, slots=True)
class RoleplaySet:
    id: UUID
    channel_id: str
    name: str
    draft: RoleplayPackage
    draft_version: int
    published: RoleplayRevision | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None


@dataclass(frozen=True, slots=True)
class RoleplayImportResult:
    """One imported character and the immutable revision selected for use."""

    roleplay_set: RoleplaySet
    revision: RoleplayRevision
    reused: bool
