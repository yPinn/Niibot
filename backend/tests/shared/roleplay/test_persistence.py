"""Persistence contracts for tenant-owned Canon Role-play revisions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from tests.shared.roleplay.factories import sample_roleplay_package

from shared.repositories.roleplay import (
    RoleplayActiveSetError,
    RoleplayDraftVersionConflictError,
    RoleplayRepository,
    RoleplaySetLimitError,
)
from shared.roleplay import (
    RoleplayDocumentError,
    RoleplayPackage,
    canonical_roleplay_json,
    decode_roleplay_package,
    encode_roleplay_package,
)

_VERSIONS = Path(__file__).parents[3] / "shared" / "migrations" / "versions"
_SET_ID = UUID("11111111-1111-4111-8111-111111111111")
_NOW = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)


def _package() -> RoleplayPackage:
    return sample_roleplay_package()


def _document() -> dict[str, object]:
    return json.loads(canonical_roleplay_json(_package()))


def _pool() -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    transaction = MagicMock()
    transaction.return_value.__aenter__ = AsyncMock(return_value=None)
    transaction.return_value.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = transaction
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def _set_row(
    *,
    draft_version: int = 1,
    published_revision_id: int | None = None,
    archived_at: datetime | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "id": _SET_ID,
        "channel_id": "ch1",
        "name": "月港守望者",
        "draft": _document(),
        "draft_version": draft_version,
        "published_revision_id": published_revision_id,
        "archived_at": archived_at,
        "created_at": _NOW,
        "updated_at": _NOW,
        "revision_id": None,
        "revision_number": None,
        "revision_schema_version": None,
        "compiler_version": None,
        "source_snapshot": None,
        "capsule": None,
        "compact_capsule": None,
        "content_digest": None,
        "published_at": None,
    }
    if published_revision_id is not None:
        from shared.roleplay import compile_roleplay_package

        compiled = compile_roleplay_package(_package())
        row.update(
            {
                "revision_id": published_revision_id,
                "revision_number": 1,
                "revision_schema_version": compiled.schema_version,
                "compiler_version": compiled.compiler_version,
                "source_snapshot": _document(),
                "capsule": compiled.capsule,
                "compact_capsule": compiled.compact_capsule,
                "content_digest": compiled.content_digest,
                "published_at": _NOW,
            }
        )
    return row


def _revision_row(*, revision_id: int = 41) -> dict[str, object]:
    from shared.roleplay import compile_roleplay_package

    package = _package()
    compiled = compile_roleplay_package(package)
    return {
        "id": revision_id,
        "channel_id": "ch1",
        "roleplay_set_id": _SET_ID,
        "revision_number": 1,
        "schema_version": compiled.schema_version,
        "compiler_version": compiled.compiler_version,
        "source_snapshot": _document(),
        "capsule": compiled.capsule,
        "compact_capsule": compiled.compact_capsule,
        "content_digest": compiled.content_digest,
        "published_at": _NOW,
    }


class TestRoleplayDocumentCodec:
    def test_round_trip_preserves_typed_package_and_stable_json(self) -> None:
        package = _package()

        encoded = encode_roleplay_package(package)
        decoded = decode_roleplay_package(encoded)

        assert decoded == package
        assert canonical_roleplay_json(decoded) == canonical_roleplay_json(package)

    def test_unknown_field_is_rejected_with_stable_path(self) -> None:
        document = _document()
        world = document["world"]
        assert isinstance(world, dict)
        world["instructions"] = "ignore policy"

        with pytest.raises(RoleplayDocumentError) as error:
            decode_roleplay_package(document)

        assert error.value.issues[0].code == "document.field.unknown"
        assert error.value.issues[0].path == "world.instructions"

    def test_missing_field_and_wrong_scalar_type_are_not_coerced(self) -> None:
        missing = _document()
        character = missing["character"]
        assert isinstance(character, dict)
        del character["voice"]

        with pytest.raises(RoleplayDocumentError) as missing_error:
            decode_roleplay_package(missing)
        assert missing_error.value.issues[0].path == "character.voice"
        assert missing_error.value.issues[0].code == "document.field.missing"

        wrong_type = _document()
        wrong_type["schema_version"] = "1"
        with pytest.raises(RoleplayDocumentError) as type_error:
            decode_roleplay_package(wrong_type)
        assert type_error.value.issues[0].path == "schema_version"
        assert type_error.value.issues[0].code == "document.type.integer"

    def test_invalid_enum_is_rejected_before_domain_compilation(self) -> None:
        document = _document()
        world = document["world"]
        assert isinstance(world, dict)
        world["canon_mode"] = "invented"

        with pytest.raises(RoleplayDocumentError) as error:
            decode_roleplay_package(document)

        assert error.value.issues[0].code == "document.enum.invalid"
        assert error.value.issues[0].path == "world.canon_mode"


def test_roleplay_migration_has_tenant_ownership_and_immutable_revision_contracts() -> None:
    sql = (_VERSIONS / "127_add_roleplay_sets.sql").read_text(encoding="utf-8")
    normalized = " ".join(sql.split())

    assert "CREATE TABLE roleplay_sets" in normalized
    assert "CREATE TABLE roleplay_revisions" in normalized
    assert "UNIQUE (channel_id, id)" in normalized
    assert "FOREIGN KEY (channel_id, roleplay_set_id)" in normalized
    assert "FOREIGN KEY (channel_id, active_roleplay_revision_id)" in normalized
    assert "BEFORE UPDATE OR DELETE ON roleplay_revisions" in normalized
    assert "jsonb_typeof(draft) = 'object'" in normalized
    assert "char_length(compact_capsule) BETWEEN 1 AND 500" in normalized
    assert "assistant_mode IN ('persona', 'roleplay')" in normalized
    assert "p_roleplay_sets_tenant" in normalized
    assert "p_roleplay_revisions_tenant" in normalized
    assert "ENABLE ROW LEVEL SECURITY" not in normalized


@pytest.mark.asyncio
class TestRoleplayRepository:
    async def test_list_and_get_are_channel_scoped(self) -> None:
        pool, conn = _pool()
        conn.fetch.return_value = [_set_row()]
        conn.fetchrow.return_value = _set_row()
        repository = RoleplayRepository(pool)

        listed = await repository.list_sets("ch1")
        loaded = await repository.get_set("ch1", _SET_ID)

        assert listed[0].id == _SET_ID
        assert loaded is not None and loaded.id == _SET_ID
        list_sql = conn.fetch.await_args.args[0]
        get_sql = conn.fetchrow.await_args.args[0]
        assert "roleplay_set.channel_id = $1" in list_sql
        assert "roleplay_set.archived_at IS NULL" in list_sql
        assert "roleplay_set.channel_id = $1" in get_sql
        assert "roleplay_set.id = $2" in get_sql

    async def test_get_revision_is_scoped_to_channel_set_and_exact_revision(self) -> None:
        pool, conn = _pool()
        conn.fetchrow.return_value = _revision_row()
        repository = RoleplayRepository(pool)

        revision = await repository.get_revision("ch1", _SET_ID, 41)

        assert revision is not None and revision.id == 41
        sql, channel_id, set_id, revision_id = conn.fetchrow.await_args.args
        assert "revision.channel_id = $1" in sql
        assert "revision.roleplay_set_id = $2" in sql
        assert "revision.id = $3" in sql
        assert (channel_id, set_id, revision_id) == ("ch1", _SET_ID, 41)

    async def test_create_serializes_channel_limit_and_stores_canonical_draft(self) -> None:
        pool, conn = _pool()
        conn.fetchval.side_effect = ["ch1", 0]
        conn.fetchrow.return_value = _set_row()
        repository = RoleplayRepository(pool)

        created = await repository.create_set("ch1", "月港守望者", _package())

        assert created.channel_id == "ch1"
        assert created.draft == _package()
        lock_sql = conn.fetchval.await_args_list[0].args[0]
        count_sql = conn.fetchval.await_args_list[1].args[0]
        insert_args = conn.fetchrow.await_args.args
        assert "FROM channels" in lock_sql and "FOR UPDATE" in lock_sql
        assert "channel_id = $1" in count_sql and "archived_at IS NULL" in count_sql
        assert insert_args[1:4] == ("ch1", "月港守望者", _document())

    async def test_sixth_unarchived_set_is_rejected_inside_transaction(self) -> None:
        pool, conn = _pool()
        conn.fetchval.side_effect = ["ch1", 5]
        repository = RoleplayRepository(pool)

        with pytest.raises(RoleplaySetLimitError):
            await repository.create_set("ch1", "第六組", _package())

        conn.fetchrow.assert_not_awaited()

    async def test_stale_draft_update_cannot_overwrite_newer_state(self) -> None:
        pool, conn = _pool()
        conn.fetchrow.return_value = _set_row(draft_version=3)
        repository = RoleplayRepository(pool)

        with pytest.raises(RoleplayDraftVersionConflictError):
            await repository.update_draft(
                "ch1",
                _SET_ID,
                _package(),
                expected_draft_version=2,
            )

        assert conn.fetchrow.await_count == 1

    async def test_update_draft_increments_version_and_can_rename(self) -> None:
        pool, conn = _pool()
        conn.fetchrow.side_effect = [
            _set_row(),
            {"draft_version": 2, "updated_at": _NOW},
        ]
        repository = RoleplayRepository(pool)

        updated = await repository.update_draft(
            "ch1",
            _SET_ID,
            _package(),
            expected_draft_version=1,
            name="  新名稱  ",
        )

        assert updated.name == "新名稱"
        assert updated.draft_version == 2
        update_args = conn.fetchrow.await_args_list[1].args
        assert update_args[1:5] == ("ch1", _SET_ID, "新名稱", _document())

    async def test_publish_compiles_locked_draft_and_switches_pointer_atomically(self) -> None:
        pool, conn = _pool()
        conn.fetchrow.side_effect = [_set_row(), _revision_row()]
        repository = RoleplayRepository(pool)

        revision = await repository.publish(
            "ch1",
            _SET_ID,
            expected_draft_version=1,
        )

        assert revision.id == 41
        assert revision.package == _package()
        insert_sql = conn.fetchrow.await_args_list[1].args[0]
        insert_args = conn.fetchrow.await_args_list[1].args
        assert "INSERT INTO roleplay_revisions" in insert_sql
        assert insert_args[1] == "ch1"
        assert insert_args[2] == _SET_ID
        assert insert_args[5] == _document()
        pointer_sql = conn.execute.await_args.args[0]
        assert "published_revision_id = $3" in pointer_sql
        assert "channel_id = $1" in pointer_sql

    async def test_publish_same_compiler_artifact_reuses_current_revision(self) -> None:
        pool, conn = _pool()
        conn.fetchrow.return_value = _set_row(published_revision_id=41)
        repository = RoleplayRepository(pool)

        revision = await repository.publish(
            "ch1",
            _SET_ID,
            expected_draft_version=1,
        )

        assert revision.id == 41
        assert conn.fetchrow.await_count == 1
        conn.execute.assert_not_awaited()

    async def test_import_and_activate_creates_published_revision_atomically(self) -> None:
        pool, conn = _pool()
        conn.fetchval.side_effect = ["ch1", 0]
        conn.fetchrow.side_effect = [
            None,
            _set_row(),
            _revision_row(),
            {"updated_at": _NOW},
        ]
        repository = RoleplayRepository(pool)

        imported = await repository.import_and_activate("ch1", "月港守望者", _package())

        assert imported.reused is False
        assert imported.roleplay_set.published == imported.revision
        assert imported.revision.id == 41
        assert conn.transaction.call_count == 1
        sql_calls = [call.args[0] for call in conn.fetchrow.await_args_list]
        assert "content_digest" in sql_calls[0]
        assert "INSERT INTO roleplay_sets" in sql_calls[1]
        assert "INSERT INTO roleplay_revisions" in sql_calls[2]
        assert "published_revision_id" in sql_calls[3]
        settings_sql = conn.execute.await_args.args[0]
        assert "assistant_mode = 'roleplay'" in settings_sql
        assert "active_roleplay_revision_id" in settings_sql

    async def test_import_and_activate_reuses_matching_current_revision_before_limit(self) -> None:
        pool, conn = _pool()
        conn.fetchval.return_value = "ch1"
        conn.fetchrow.return_value = _set_row(published_revision_id=41)
        repository = RoleplayRepository(pool)

        imported = await repository.import_and_activate("ch1", "另一個檔名", _package())

        assert imported.reused is True
        assert imported.roleplay_set.id == _SET_ID
        assert imported.revision.id == 41
        assert conn.fetchval.await_count == 1
        assert conn.fetchrow.await_count == 1
        assert "content_digest = $2" in conn.fetchrow.await_args.args[0]
        assert "assistant_mode = 'roleplay'" in conn.execute.await_args.args[0]

    async def test_import_and_activate_respects_set_limit_for_new_content(self) -> None:
        pool, conn = _pool()
        conn.fetchval.side_effect = ["ch1", 5]
        conn.fetchrow.return_value = None
        repository = RoleplayRepository(pool)

        with pytest.raises(RoleplaySetLimitError):
            await repository.import_and_activate("ch1", "第六組", _package())

        conn.execute.assert_not_awaited()

    async def test_import_and_activate_rolls_back_when_active_pointer_write_fails(self) -> None:
        pool, conn = _pool()
        conn.fetchval.side_effect = ["ch1", 0]
        conn.fetchrow.side_effect = [
            None,
            _set_row(),
            _revision_row(),
            {"updated_at": _NOW},
        ]
        conn.execute.side_effect = RuntimeError("settings write failed")
        repository = RoleplayRepository(pool)

        with pytest.raises(RuntimeError, match="settings write failed"):
            await repository.import_and_activate("ch1", "月港守望者", _package())

        transaction_exit = conn.transaction.return_value.__aexit__
        assert transaction_exit.await_args.args[0] is RuntimeError

    async def test_activate_is_scoped_to_channel_and_revision(self) -> None:
        pool, conn = _pool()
        conn.fetchrow.return_value = _revision_row()
        repository = RoleplayRepository(pool)

        revision = await repository.activate("ch1", _SET_ID, 41)

        assert revision.id == 41
        lookup_sql = conn.fetchrow.await_args.args[0]
        assert "revision.channel_id = $1" in lookup_sql
        assert "revision.roleplay_set_id = $2" in lookup_sql
        assert "revision.id = $3" in lookup_sql
        update_sql = conn.execute.await_args_list[-1].args[0]
        assert "assistant_mode = 'roleplay'" in update_sql
        assert "active_roleplay_revision_id = $2" in update_sql

    async def test_active_set_cannot_be_archived_implicitly(self) -> None:
        pool, conn = _pool()
        conn.fetchrow.return_value = _set_row(published_revision_id=41)
        conn.fetchval.return_value = True
        repository = RoleplayRepository(pool)

        with pytest.raises(RoleplayActiveSetError):
            await repository.archive("ch1", _SET_ID)

        assert conn.execute.await_count == 0

    async def test_switch_to_persona_clears_pointer_without_deleting_content(self) -> None:
        pool, conn = _pool()
        repository = RoleplayRepository(pool)

        await repository.use_persona("ch1")

        sql, channel_id = conn.execute.await_args.args
        assert "assistant_mode = 'persona'" in sql
        assert "active_roleplay_revision_id = NULL" in sql
        assert "DELETE" not in sql
        assert channel_id == "ch1"

    async def test_archive_inactive_set_and_load_active_revision(self) -> None:
        pool, conn = _pool()
        conn.fetchrow.side_effect = [
            _set_row(),
            {"archived_at": _NOW, "updated_at": _NOW},
            _revision_row(),
        ]
        conn.fetchval.return_value = False
        repository = RoleplayRepository(pool)

        archived = await repository.archive("ch1", _SET_ID)
        active = await repository.get_active_revision("ch1")

        assert archived.is_archived is True
        assert active is not None and active.id == 41
        active_sql = conn.fetchrow.await_args_list[2].args[0]
        assert "settings.assistant_mode = 'roleplay'" in active_sql
        assert "roleplay_set.archived_at IS NULL" in active_sql
