"""Tenant-scoped application boundary for Canon Role-play authoring."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, NoReturn
from uuid import UUID

import asyncpg

from shared.assistant import (
    ASSISTANT_SCOPE_CHANGED_CHANNEL,
    AssistantMode,
    AssistantScopeChange,
)
from shared.errors import AppError, ConflictError, NotFoundError
from shared.models.roleplay import RoleplayRevision, RoleplaySet
from shared.repositories.roleplay import (
    RoleplayActiveSetError,
    RoleplayDraftVersionConflictError,
    RoleplayPersistenceError,
    RoleplayRepository,
    RoleplayRevisionOwnershipError,
    RoleplaySetArchivedError,
    RoleplaySetLimitError,
    RoleplaySetNotFoundError,
)
from shared.roleplay import (
    RoleplayDocumentError,
    RoleplayPackage,
    RoleplayValidationError,
    decode_roleplay_package,
)
from shared.roleplay.portable import (
    PortableRoleplayCharacter,
    RoleplayPortableError,
    build_roleplay_character_export,
    decode_roleplay_character_export,
)


class RoleplayNotFoundApiError(NotFoundError):
    code = "ROLEPLAY.NOT_FOUND"
    user_message = "找不到這個角色設定集"


class RoleplayDocumentInvalidError(AppError):
    code = "ROLEPLAY.DOCUMENT_INVALID"
    http_status = 422
    user_message = "角色設定內容有誤，請檢查標示欄位"


class RoleplayPublishInvalidError(AppError):
    code = "ROLEPLAY.PUBLISH_INVALID"
    http_status = 422
    user_message = "角色設定尚未完整，請檢查標示欄位"


class RoleplayDraftConflictApiError(ConflictError):
    code = "ROLEPLAY.VERSION_CONFLICT"
    user_message = "內容已被更新，請重新載入後再試"


class RoleplaySetLimitApiError(ConflictError):
    code = "ROLEPLAY.SET_LIMIT"
    user_message = "角色設定集已達上限，請先封存一組"


class RoleplaySetArchivedApiError(ConflictError):
    code = "ROLEPLAY.SET_ARCHIVED"
    user_message = "這個角色設定集已封存"


class RoleplayActiveSetApiError(ConflictError):
    code = "ROLEPLAY.SET_ACTIVE"
    user_message = "這個角色正在使用中，請先切換角色"


class RoleplayImportInvalidError(AppError):
    code = "ROLEPLAY.IMPORT_INVALID"
    http_status = 422
    user_message = "角色設定集無法匯入，請確認檔案內容"


class RoleplayImportTooLargeError(AppError):
    code = "ROLEPLAY.IMPORT_TOO_LARGE"
    http_status = 422
    user_message = "角色設定集超過大小上限，請確認檔案"


@dataclass(frozen=True, slots=True)
class RoleplayImportOutcome:
    mode: Literal["use", "copy"]
    roleplay_set: RoleplaySet
    revision: RoleplayRevision | None
    reused: bool


class RoleplayService:
    """Decode untrusted documents, map domain failures, and emit scope changes."""

    def __init__(
        self,
        repository: RoleplayRepository,
        pool: asyncpg.Pool,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.pool = pool
        self._clock = clock or (lambda: datetime.now(UTC))

    async def list_sets(
        self, channel_id: str, *, include_archived: bool = False
    ) -> tuple[RoleplaySet, ...]:
        return await self.repository.list_sets(channel_id, include_archived=include_archived)

    async def get_set(self, channel_id: str, roleplay_set_id: UUID) -> RoleplaySet:
        result = await self.repository.get_set(channel_id, roleplay_set_id)
        if result is None:
            raise RoleplayNotFoundApiError()
        return result

    async def export_revision(
        self,
        channel_id: str,
        roleplay_set_id: UUID,
        revision_id: int,
    ) -> dict[str, object]:
        roleplay_set = await self.get_set(channel_id, roleplay_set_id)
        revision = await self.repository.get_revision(
            channel_id,
            roleplay_set_id,
            revision_id,
        )
        if revision is None:
            raise RoleplayNotFoundApiError()
        return build_roleplay_character_export(
            display_name=roleplay_set.name,
            package=revision.package,
            compiled=revision.compiled,
            exported_at=self._clock(),
        )

    async def import_character(
        self,
        channel_id: str,
        *,
        mode: Literal["use", "copy"],
        character: object,
    ) -> RoleplayImportOutcome:
        portable = self._decode_portable(character)
        try:
            if mode == "copy":
                roleplay_set = await self.repository.create_set(
                    channel_id,
                    portable.display_name,
                    portable.package,
                )
                return RoleplayImportOutcome(
                    mode=mode,
                    roleplay_set=roleplay_set,
                    revision=None,
                    reused=False,
                )

            imported = await self.repository.import_and_activate(
                channel_id,
                portable.display_name,
                portable.package,
            )
        except RoleplayPersistenceError as error:
            self._raise_persistence(error)
        except ValueError:
            raise RoleplayImportInvalidError() from None

        await self._notify_scope_change(
            channel_id,
            assistant_mode=AssistantMode.ROLEPLAY,
            active_roleplay_revision_id=imported.revision.id,
        )
        return RoleplayImportOutcome(
            mode=mode,
            roleplay_set=imported.roleplay_set,
            revision=imported.revision,
            reused=imported.reused,
        )

    async def create_set(
        self,
        channel_id: str,
        *,
        name: str,
        draft: object,
    ) -> RoleplaySet:
        package = self._decode_document(draft)
        try:
            return await self.repository.create_set(channel_id, name, package)
        except RoleplayPersistenceError as error:
            self._raise_persistence(error)
        except ValueError:
            raise RoleplayDocumentInvalidError(
                fields={"name": "名稱必須介於 1 到 100 字"}
            ) from None

    async def update_draft(
        self,
        channel_id: str,
        roleplay_set_id: UUID,
        *,
        draft: object,
        expected_draft_version: int,
        name: str | None,
    ) -> RoleplaySet:
        package = self._decode_document(draft)
        try:
            return await self.repository.update_draft(
                channel_id,
                roleplay_set_id,
                package,
                expected_draft_version=expected_draft_version,
                name=name,
            )
        except RoleplayPersistenceError as error:
            self._raise_persistence(error)
        except ValueError:
            raise RoleplayDocumentInvalidError(
                fields={"name": "名稱必須介於 1 到 100 字"}
            ) from None

    async def publish(
        self,
        channel_id: str,
        roleplay_set_id: UUID,
        *,
        expected_draft_version: int,
    ) -> RoleplayRevision:
        try:
            return await self.repository.publish(
                channel_id,
                roleplay_set_id,
                expected_draft_version=expected_draft_version,
            )
        except RoleplayValidationError as error:
            raise RoleplayPublishInvalidError(
                fields={issue.path: issue.message for issue in error.issues},
                context={"issue_codes": [issue.code for issue in error.issues]},
            ) from None
        except RoleplayPersistenceError as error:
            self._raise_persistence(error)

    async def activate(
        self,
        channel_id: str,
        roleplay_set_id: UUID,
        *,
        revision_id: int,
    ) -> RoleplayRevision:
        try:
            revision = await self.repository.activate(
                channel_id,
                roleplay_set_id,
                revision_id,
            )
        except RoleplayPersistenceError as error:
            self._raise_persistence(error)
        await self._notify_scope_change(
            channel_id,
            assistant_mode=AssistantMode.ROLEPLAY,
            active_roleplay_revision_id=revision.id,
        )
        return revision

    async def use_persona(self, channel_id: str) -> None:
        await self.repository.use_persona(channel_id)
        await self._notify_scope_change(
            channel_id,
            assistant_mode=AssistantMode.PERSONA,
            active_roleplay_revision_id=None,
        )

    async def archive(self, channel_id: str, roleplay_set_id: UUID) -> RoleplaySet:
        try:
            return await self.repository.archive(channel_id, roleplay_set_id)
        except RoleplayPersistenceError as error:
            self._raise_persistence(error)

    @staticmethod
    def _decode_document(value: object) -> RoleplayPackage:
        try:
            return decode_roleplay_package(value)
        except RoleplayDocumentError as error:
            raise RoleplayDocumentInvalidError(
                fields={issue.path: issue.message for issue in error.issues},
                context={"issue_codes": [issue.code for issue in error.issues]},
            ) from None

    @staticmethod
    def _decode_portable(value: object) -> PortableRoleplayCharacter:
        try:
            return decode_roleplay_character_export(value)
        except RoleplayPortableError as error:
            raise RoleplayImportInvalidError(
                fields={error.issue.path: error.issue.message},
                context={"issue_code": error.issue.code},
            ) from None

    @staticmethod
    def _raise_persistence(error: RoleplayPersistenceError) -> NoReturn:
        if isinstance(error, (RoleplaySetNotFoundError, RoleplayRevisionOwnershipError)):
            raise RoleplayNotFoundApiError() from None
        if isinstance(error, RoleplayDraftVersionConflictError):
            raise RoleplayDraftConflictApiError() from None
        if isinstance(error, RoleplaySetLimitError):
            raise RoleplaySetLimitApiError() from None
        if isinstance(error, RoleplaySetArchivedError):
            raise RoleplaySetArchivedApiError() from None
        if isinstance(error, RoleplayActiveSetError):
            raise RoleplayActiveSetApiError() from None
        raise error

    async def _notify_scope_change(
        self,
        channel_id: str,
        *,
        assistant_mode: AssistantMode,
        active_roleplay_revision_id: int | None,
    ) -> None:
        payload = AssistantScopeChange(
            channel_id=channel_id,
            assistant_mode=assistant_mode,
            active_roleplay_revision_id=active_roleplay_revision_id,
        ).to_payload()
        async with self.pool.acquire() as conn:
            await conn.execute(
                "SELECT pg_notify($1, $2)",
                ASSISTANT_SCOPE_CHANGED_CHANNEL,
                payload,
            )
