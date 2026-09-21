"""Portable check-in export and bounded destructive data-management tests."""

from __future__ import annotations

import csv
import io
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.checkin_data_service import (
    CheckinClearScope,
    CheckinDataService,
    CheckinExportRow,
    encode_checkin_export_csv,
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


def _summary_row() -> dict[str, int]:
    return {
        "participant_count": 2,
        "total_days": 19,
        "imported_viewers": 1,
        "imported_days": 15,
        "ledger_checkins": 4,
        "card_draws": 4,
        "checkin_events": 4,
    }


@pytest.mark.asyncio
async def test_export_combines_carryover_and_ledger_into_reimportable_rows() -> None:
    pool, conn = _pool()
    conn.fetch.return_value = [
        {
            "user_id": "101",
            "username": "alice",
            "display_name": "Alice",
            "total_days": 16,
            "last_checkin_date": date(2026, 9, 11),
            "current_streak": 4,
            "daily_order": 2,
        }
    ]

    rows = await CheckinDataService(pool).list_export_rows("channel-1")

    assert rows == [
        CheckinExportRow(
            user_id="101",
            username="alice",
            display_name="Alice",
            total_days=16,
            last_checkin_date=date(2026, 9, 11),
            current_streak=4,
            daily_order=2,
        )
    ]
    query = conn.fetch.await_args.args[0]
    assert "FULL OUTER JOIN" in query
    assert "source_daily_order" in query
    assert "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW" in query
    assert conn.fetch.await_args.args[1:] == ("channel-1",)


def test_csv_export_is_bom_prefixed_and_guards_spreadsheet_formulas() -> None:
    payload = encode_checkin_export_csv(
        [
            CheckinExportRow(
                user_id="101",
                username="  +alice",
                display_name='=IMPORTXML("https://example.invalid")',
                total_days=16,
                last_checkin_date=date(2026, 9, 11),
                current_streak=4,
                daily_order=2,
            )
        ]
    )

    assert payload.startswith(b"\xef\xbb\xbf")
    decoded = payload.decode("utf-8-sig")
    parsed = list(csv.reader(io.StringIO(decoded)))
    assert parsed[0] == [
        "Username",
        "Twitch User ID",
        "DisplayName",
        "Count",
        "LastDate",
        "Streak",
        "TodayOrder",
    ]
    assert parsed[1] == [
        "'  +alice",
        "101",
        '\'=IMPORTXML("https://example.invalid")',
        "16",
        "2026-09-11",
        "4",
        "2",
    ]


@pytest.mark.asyncio
async def test_summary_reports_imported_and_full_reset_impact_separately() -> None:
    pool, conn = _pool()
    conn.fetchrow.return_value = _summary_row()

    summary = await CheckinDataService(pool).get_summary("channel-1")

    assert summary.participant_count == 2
    assert summary.total_days == 19
    assert summary.imported_viewers == 1
    assert summary.imported_days == 15
    assert summary.ledger_checkins == 4
    assert summary.card_draws == 4
    assert summary.checkin_events == 4
    assert conn.fetchrow.await_args.args[1:] == ("channel-1",)


@pytest.mark.asyncio
async def test_clear_imported_rebuilds_streaks_from_real_ledger_and_keeps_draws() -> None:
    pool, conn = _pool()
    conn.fetchrow.return_value = _summary_row()
    service = CheckinDataService(pool)

    result = await service.clear(
        channel_id="channel-1",
        actor_user_id="00000000-0000-0000-0000-000000000001",
        scope=CheckinClearScope.IMPORTED,
    )

    assert result.scope is CheckinClearScope.IMPORTED
    assert result.imported_viewers == 1
    sql = "\n".join(call.args[0] for call in conn.execute.await_args_list)
    assert "pg_advisory_xact_lock" in sql
    assert "DELETE FROM viewer_checkin_carryovers" in sql
    assert "DELETE FROM checkin_import_batches" in sql
    assert "DELETE FROM viewer_daily_checkin_streaks" in sql
    assert "INSERT INTO viewer_daily_checkin_streaks" in sql
    assert "DELETE FROM viewer_checkins" not in sql
    assert "DELETE FROM viewer_card_draws" not in sql
    assert "checkin.data_cleared" in sql
    conn.transaction.assert_called_once_with()


@pytest.mark.asyncio
async def test_clear_all_deletes_checkins_then_their_draws_and_retains_settings() -> None:
    pool, conn = _pool()
    conn.fetchrow.return_value = _summary_row()
    service = CheckinDataService(pool)

    result = await service.clear(
        channel_id="channel-1",
        actor_user_id="00000000-0000-0000-0000-000000000001",
        scope=CheckinClearScope.ALL,
    )

    assert result.scope is CheckinClearScope.ALL
    sql_calls = [call.args[0] for call in conn.execute.await_args_list]
    joined = "\n".join(sql_calls)
    draw_index = next(
        i for i, sql in enumerate(sql_calls) if "DELETE FROM viewer_card_draws" in sql
    )
    checkin_index = next(
        i for i, sql in enumerate(sql_calls) if "DELETE FROM viewer_checkins" in sql
    )
    # The FK is deferred. Removing the parent first gives the immutable-draw
    # trigger a narrow, auditable signal that this is a deliberate reset.
    assert checkin_index < draw_index
    assert "event_type = 'checkin.recorded'" in joined
    assert "DELETE FROM viewer_daily_checkin_streaks" in joined
    assert "DELETE FROM viewer_checkin_carryovers" in joined
    assert "DELETE FROM checkin_import_batches" in joined
    assert "DELETE FROM checkin_settings" not in joined
    assert "checkin.data_cleared" in joined
