"""Check-in carry-over preview, identity resolution, and atomic apply tests."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.checkin_import.formats import parse_summary_bytes
from services.checkin_import.models import (
    IdentityRemap,
    IdentityResolution,
    IdentityTargetType,
    ImportRowStatus,
)
from services.checkin_import.service import (
    CheckinImportConflictError,
    CheckinImportService,
    PreviewNotFoundError,
    load_preview,
    stash_preview,
)


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


def _parsed(payload: bytes | None = None):
    return parse_summary_bytes(
        "checkins.csv",
        payload or b"Username,Count,LastDate,Streak,TodayOrder\nalice,15,2026-09-10,3,5\n",
        through_date=date(2026, 9, 10),
    )


@pytest.mark.asyncio
async def test_preview_batch_resolves_logins_to_stable_twitch_ids() -> None:
    pool, conn = _pool()
    conn.fetch.return_value = []
    twitch = MagicMock()
    twitch.get_users_by_logins_strict = AsyncMock(
        return_value=[{"id": "101", "login": "alice", "display_name": "Alice"}]
    )
    service = CheckinImportService(pool, twitch)

    preview = await service.preview(
        channel_id="channel-1",
        source="chiwabots",
        source_timezone="Asia/Taipei",
        through_date=date(2026, 9, 10),
        parsed=_parsed(),
        today=date(2026, 9, 10),
    )

    assert preview.rows[0].status is ImportRowStatus.READY
    assert preview.rows[0].user_id == "101"
    assert preview.rows[0].username == "alice"
    twitch.get_users_by_logins_strict.assert_awaited_once_with(["alice"])


@pytest.mark.asyncio
async def test_preview_resolves_uid_only_to_current_twitch_names() -> None:
    pool, conn = _pool()
    conn.fetch.return_value = []
    twitch = MagicMock()
    twitch.get_users_by_ids_strict = AsyncMock(
        return_value=[{"id": "101", "login": "alice", "display_name": "Alice"}]
    )
    service = CheckinImportService(pool, twitch)

    preview = await service.preview(
        channel_id="channel-1",
        source="other-bot",
        source_timezone="UTC",
        through_date=date(2026, 9, 10),
        parsed=_parsed(b"Twitch User ID,Count,LastDate\n101,15,2026-09-10\n"),
        today=date(2026, 9, 10),
    )

    row = preview.rows[0]
    assert row.status is ImportRowStatus.READY
    assert row.user_id == "101"
    assert row.username == "alice"
    assert row.display_name == "Alice"
    assert row.identity_resolution is IdentityResolution.TWITCH_ID


@pytest.mark.asyncio
async def test_preview_uses_uid_as_authority_when_source_username_is_stale() -> None:
    pool, conn = _pool()
    conn.fetch.return_value = []
    twitch = MagicMock()
    twitch.get_users_by_ids_strict = AsyncMock(
        return_value=[{"id": "101", "login": "alice_new", "display_name": "Alice New"}]
    )
    twitch.get_users_by_logins_strict = AsyncMock(return_value=[])
    service = CheckinImportService(pool, twitch)
    parsed = _parsed(
        b"Twitch User ID,Username,DisplayName,Count,LastDate\n"
        b"101,alice_old,Legacy Alice,15,2026-09-10\n"
    )

    preview = await service.preview(
        channel_id="channel-1",
        source="other-bot",
        source_timezone="UTC",
        through_date=date(2026, 9, 10),
        parsed=parsed,
        today=date(2026, 9, 10),
    )

    row = preview.rows[0]
    assert row.status is ImportRowStatus.REVIEW
    assert row.user_id == "101"
    assert row.username == "alice_new"
    assert row.display_name == "Alice New"
    assert row.source_username == "alice_old"
    assert row.source_display_name == "Legacy Alice"
    assert row.identity_resolution is IdentityResolution.TWITCH_ID


@pytest.mark.asyncio
async def test_preview_rejects_uid_and_current_username_pointing_to_different_users() -> None:
    pool, conn = _pool()
    conn.fetch.return_value = []
    twitch = MagicMock()
    twitch.get_users_by_ids_strict = AsyncMock(
        return_value=[{"id": "101", "login": "alice_new", "display_name": "Alice New"}]
    )
    twitch.get_users_by_logins_strict = AsyncMock(
        return_value=[{"id": "202", "login": "alice_old", "display_name": "Other Alice"}]
    )
    service = CheckinImportService(pool, twitch)

    preview = await service.preview(
        channel_id="channel-1",
        source="other-bot",
        source_timezone="UTC",
        through_date=date(2026, 9, 10),
        parsed=_parsed(b"Twitch User ID,Username,Count,LastDate\n101,alice_old,15,2026-09-10\n"),
        today=date(2026, 9, 10),
    )

    assert preview.rows[0].status is ImportRowStatus.CONFLICT
    assert "不同" in "".join(preview.rows[0].issues)


@pytest.mark.asyncio
async def test_preview_reviews_display_name_only_when_it_is_an_exact_login() -> None:
    pool, conn = _pool()
    conn.fetch.return_value = []
    twitch = MagicMock()
    twitch.get_users_by_logins_strict = AsyncMock(
        return_value=[{"id": "101", "login": "alice", "display_name": "Alice"}]
    )
    service = CheckinImportService(pool, twitch)

    preview = await service.preview(
        channel_id="channel-1",
        source="other-bot",
        source_timezone="UTC",
        through_date=date(2026, 9, 10),
        parsed=_parsed(b"DisplayName,Count,LastDate\nAlice,15,2026-09-10\n"),
        today=date(2026, 9, 10),
    )

    row = preview.rows[0]
    assert row.status is ImportRowStatus.REVIEW
    assert row.user_id == "101"
    assert row.source_display_name == "Alice"
    assert row.identity_resolution is IdentityResolution.DISPLAY_AS_LOGIN


@pytest.mark.asyncio
async def test_preview_keeps_non_login_display_name_unresolved() -> None:
    pool, conn = _pool()
    conn.fetch.return_value = []
    twitch = MagicMock()
    twitch.get_users_by_logins_strict = AsyncMock(return_value=[])
    service = CheckinImportService(pool, twitch)

    preview = await service.preview(
        channel_id="channel-1",
        source="other-bot",
        source_timezone="UTC",
        through_date=date(2026, 9, 10),
        parsed=_parsed("DisplayName,Count,LastDate\n愛麗絲,15,2026-09-10\n".encode()),
        today=date(2026, 9, 10),
    )

    row = preview.rows[0]
    assert row.status is ImportRowStatus.UNRESOLVED
    assert row.user_id is None
    assert row.username is None
    assert row.source_display_name == "愛麗絲"
    twitch.get_users_by_logins_strict.assert_not_awaited()


@pytest.mark.asyncio
async def test_preview_marks_missing_and_existing_viewers_without_inventing_ids() -> None:
    pool, conn = _pool()
    conn.fetch.return_value = [{"user_id": "101"}]
    twitch = MagicMock()
    twitch.get_users_by_logins_strict = AsyncMock(
        return_value=[{"id": "101", "login": "alice", "display_name": "Alice"}]
    )
    service = CheckinImportService(pool, twitch)
    parsed = _parsed(b"Username,Count,LastDate\nalice,15,2026-09-10\ngone_user,2,2026-09-09\n")

    preview = await service.preview(
        channel_id="channel-1",
        source="other-bot",
        source_timezone="UTC",
        through_date=date(2026, 9, 10),
        parsed=parsed,
        today=date(2026, 9, 10),
    )

    assert [row.status for row in preview.rows] == [
        ImportRowStatus.CONFLICT,
        ImportRowStatus.UNRESOLVED,
    ]
    assert preview.rows[1].user_id is None


@pytest.mark.asyncio
async def test_preview_keeps_invalid_rows_visible_but_not_selectable() -> None:
    pool, conn = _pool()
    conn.fetch.return_value = []
    service = CheckinImportService(pool, MagicMock())
    parsed = _parsed(b"Username,Count,LastDate\nalice,0,2026-09-10\n")

    preview = await service.preview(
        channel_id="channel-1",
        source="other-bot",
        source_timezone="UTC",
        through_date=date(2026, 9, 10),
        parsed=parsed,
        today=date(2026, 9, 10),
    )

    assert preview.rows[0].status is ImportRowStatus.INVALID
    assert preview.rows[0].user_id is None
    assert preview.rows[0].issues


@pytest.mark.asyncio
async def test_preview_batches_twitch_lookups_at_one_hundred() -> None:
    pool, conn = _pool()
    conn.fetch.return_value = []
    twitch = MagicMock()

    async def lookup(logins: list[str]):
        return [
            {"id": str(i), "login": login, "display_name": login} for i, login in enumerate(logins)
        ]

    twitch.get_users_by_logins_strict = AsyncMock(side_effect=lookup)
    rows = ["Username,Count,LastDate"] + [f"viewer_{index},1,2026-09-10" for index in range(101)]
    service = CheckinImportService(pool, twitch)

    await service.preview(
        channel_id="channel-1",
        source="other-bot",
        source_timezone="UTC",
        through_date=date(2026, 9, 10),
        parsed=_parsed("\n".join(rows).encode()),
        today=date(2026, 9, 10),
    )

    assert [len(call.args[0]) for call in twitch.get_users_by_logins_strict.await_args_list] == [
        100,
        1,
    ]


def test_preview_cache_is_bound_to_user_and_channel() -> None:
    preview = MagicMock()
    import_id = stash_preview("user-1", "channel-1", preview)

    assert load_preview("user-1", "channel-1", import_id) is preview
    with pytest.raises(PreviewNotFoundError):
        load_preview("user-2", "channel-1", import_id)
    with pytest.raises(PreviewNotFoundError):
        load_preview("user-1", "channel-2", import_id)


@pytest.mark.asyncio
async def test_manual_mapping_resolves_old_username_to_reviewable_current_account() -> None:
    pool, conn = _pool()
    conn.fetch.return_value = []
    twitch = MagicMock()
    twitch.get_users_by_logins_strict = AsyncMock(
        side_effect=[[], [{"id": "101", "login": "alice_new", "display_name": "Alice New"}]]
    )
    service = CheckinImportService(pool, twitch)
    preview = await service.preview(
        channel_id="channel-1",
        source="other-bot",
        source_timezone="UTC",
        through_date=date(2026, 9, 10),
        parsed=_parsed(b"Username,Count,LastDate\nalice_old,15,2026-09-10\n"),
        today=date(2026, 9, 10),
    )

    remapped = await service.remap_identities(
        channel_id="channel-1",
        preview=preview,
        mappings=(
            IdentityRemap(
                row_key=preview.rows[0].key,
                target_type=IdentityTargetType.USERNAME,
                value="alice_new",
            ),
        ),
    )

    row = remapped.rows[0]
    assert row.status is ImportRowStatus.REVIEW
    assert row.user_id == "101"
    assert row.username == "alice_new"
    assert row.source_username == "alice_old"
    assert row.identity_resolution is IdentityResolution.MANUAL


@pytest.mark.asyncio
async def test_manual_mapping_accepts_a_verified_current_uid() -> None:
    pool, conn = _pool()
    conn.fetch.return_value = []
    twitch = MagicMock()
    twitch.get_users_by_logins_strict = AsyncMock(return_value=[])
    twitch.get_users_by_ids_strict = AsyncMock(
        return_value=[{"id": "101", "login": "alice_new", "display_name": "Alice New"}]
    )
    service = CheckinImportService(pool, twitch)
    preview = await service.preview(
        channel_id="channel-1",
        source="other-bot",
        source_timezone="UTC",
        through_date=date(2026, 9, 10),
        parsed=_parsed(b"Username,Count,LastDate\nalice_old,15,2026-09-10\n"),
        today=date(2026, 9, 10),
    )

    remapped = await service.remap_identities(
        channel_id="channel-1",
        preview=preview,
        mappings=(
            IdentityRemap(
                row_key=preview.rows[0].key,
                target_type=IdentityTargetType.USER_ID,
                value="101",
            ),
        ),
    )

    row = remapped.rows[0]
    assert row.status is ImportRowStatus.REVIEW
    assert row.user_id == "101"
    assert row.username == "alice_new"
    assert row.identity_resolution is IdentityResolution.MANUAL
    twitch.get_users_by_ids_strict.assert_awaited_once_with(["101"])


@pytest.mark.asyncio
async def test_manual_mapping_keeps_an_unverified_target_unresolved() -> None:
    pool, conn = _pool()
    conn.fetch.return_value = []
    twitch = MagicMock()
    twitch.get_users_by_logins_strict = AsyncMock(side_effect=[[], []])
    service = CheckinImportService(pool, twitch)
    preview = await service.preview(
        channel_id="channel-1",
        source="other-bot",
        source_timezone="UTC",
        through_date=date(2026, 9, 10),
        parsed=_parsed(b"Username,Count,LastDate\nalice_old,15,2026-09-10\n"),
        today=date(2026, 9, 10),
    )

    remapped = await service.remap_identities(
        channel_id="channel-1",
        preview=preview,
        mappings=(
            IdentityRemap(
                row_key=preview.rows[0].key,
                target_type=IdentityTargetType.USERNAME,
                value="missing_user",
            ),
        ),
    )

    row = remapped.rows[0]
    assert row.status is ImportRowStatus.UNRESOLVED
    assert row.user_id is None
    assert row.source_username == "alice_old"
    assert row.issues == ("找不到指定的 Twitch 帳號，請重新輸入",)


@pytest.mark.asyncio
async def test_manual_mapping_marks_duplicate_target_uid_as_conflict() -> None:
    pool, conn = _pool()
    conn.fetch.return_value = []
    twitch = MagicMock()
    twitch.get_users_by_logins_strict = AsyncMock(
        side_effect=[
            [{"id": "101", "login": "alice", "display_name": "Alice"}],
            [{"id": "101", "login": "alice", "display_name": "Alice"}],
        ]
    )
    service = CheckinImportService(pool, twitch)
    preview = await service.preview(
        channel_id="channel-1",
        source="other-bot",
        source_timezone="UTC",
        through_date=date(2026, 9, 10),
        parsed=_parsed(b"Username,Count,LastDate\nalice,15,2026-09-10\nalice_old,2,2026-09-09\n"),
        today=date(2026, 9, 10),
    )

    remapped = await service.remap_identities(
        channel_id="channel-1",
        preview=preview,
        mappings=(
            IdentityRemap(
                row_key=preview.rows[1].key,
                target_type=IdentityTargetType.USERNAME,
                value="alice",
            ),
        ),
    )

    assert [row.status for row in remapped.rows] == [
        ImportRowStatus.CONFLICT,
        ImportRowStatus.CONFLICT,
    ]


@pytest.mark.asyncio
async def test_apply_is_atomic_and_writes_carryover_without_fake_ledger_rows() -> None:
    pool, conn = _pool()
    conn.fetch.side_effect = [[], []]
    conn.fetchrow.side_effect = [None, {"id": "batch-1"}]
    twitch = MagicMock()
    twitch.get_users_by_logins_strict = AsyncMock(
        return_value=[{"id": "101", "login": "alice", "display_name": "Alice"}]
    )
    service = CheckinImportService(pool, twitch)
    preview = await service.preview(
        channel_id="channel-1",
        source="chiwabots",
        source_timezone="Asia/Taipei",
        through_date=date(2026, 9, 10),
        parsed=_parsed(),
        today=date(2026, 9, 10),
    )

    result = await service.apply(
        channel_id="channel-1",
        actor_user_id="00000000-0000-0000-0000-000000000001",
        preview=preview,
        selected_keys=[preview.rows[0].key],
        old_source_disabled=True,
    )

    assert result.batch_id == "batch-1"
    assert result.imported_rows == 1
    conn.transaction.assert_called_once_with()
    assert "pg_advisory_xact_lock" in conn.execute.await_args_list[0].args[0]
    sql_calls = "\n".join(call.args[0] for call in conn.fetchrow.await_args_list)
    assert "INSERT INTO checkin_import_batches" in sql_calls
    assert "viewer_checkins" not in sql_calls
    assert conn.executemany.await_count == 2
    assert "viewer_checkin_carryovers" in conn.executemany.await_args_list[0].args[0]
    assert "viewer_daily_checkin_streaks" in conn.executemany.await_args_list[1].args[0]


@pytest.mark.asyncio
async def test_apply_accepts_an_explicitly_selected_review_row() -> None:
    pool, conn = _pool()
    conn.fetch.side_effect = [[], []]
    conn.fetchrow.side_effect = [None, {"id": "batch-1"}]
    twitch = MagicMock()
    twitch.get_users_by_logins_strict = AsyncMock(
        return_value=[{"id": "101", "login": "alice", "display_name": "Alice"}]
    )
    service = CheckinImportService(pool, twitch)
    preview = await service.preview(
        channel_id="channel-1",
        source="other-bot",
        source_timezone="UTC",
        through_date=date(2026, 9, 10),
        parsed=_parsed(b"DisplayName,Count,LastDate\nAlice,15,2026-09-10\n"),
        today=date(2026, 9, 10),
    )

    result = await service.apply(
        channel_id="channel-1",
        actor_user_id="00000000-0000-0000-0000-000000000001",
        preview=preview,
        selected_keys=[preview.rows[0].key],
        old_source_disabled=True,
    )

    assert result.imported_rows == 1


@pytest.mark.asyncio
async def test_apply_fails_whole_batch_when_viewer_became_a_conflict() -> None:
    pool, conn = _pool()
    conn.fetch.side_effect = [[], [{"user_id": "101"}]]
    conn.fetchrow.return_value = None
    twitch = MagicMock()
    twitch.get_users_by_logins_strict = AsyncMock(
        return_value=[{"id": "101", "login": "alice", "display_name": "Alice"}]
    )
    service = CheckinImportService(pool, twitch)
    preview = await service.preview(
        channel_id="channel-1",
        source="chiwabots",
        source_timezone="Asia/Taipei",
        through_date=date(2026, 9, 10),
        parsed=_parsed(),
        today=date(2026, 9, 10),
    )

    with pytest.raises(CheckinImportConflictError):
        await service.apply(
            channel_id="channel-1",
            actor_user_id="00000000-0000-0000-0000-000000000001",
            preview=preview,
            selected_keys=[preview.rows[0].key],
            old_source_disabled=True,
        )

    conn.executemany.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_requires_source_disabled_confirmation() -> None:
    pool, _ = _pool()
    service = CheckinImportService(pool, MagicMock())
    preview = MagicMock(rows=())

    with pytest.raises(ValueError, match="disabled"):
        await service.apply(
            channel_id="channel-1",
            actor_user_id="00000000-0000-0000-0000-000000000001",
            preview=preview,
            selected_keys=["row"],
            old_source_disabled=False,
        )
