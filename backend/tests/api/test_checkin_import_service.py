"""Check-in carry-over preview, identity resolution, and atomic apply tests."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.checkin_import.formats import parse_summary_bytes
from services.checkin_import.models import ImportRowStatus
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
