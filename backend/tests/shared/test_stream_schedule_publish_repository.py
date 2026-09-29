from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

from shared.models.stream_schedule import ScheduleKind
from shared.repositories.stream_schedule_publish import StreamSchedulePublishRepository


def _pool() -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=None)
    transaction.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=transaction)

    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


async def test_claim_due_job_uses_skip_locked_and_returns_generation() -> None:
    pool, conn = _pool()
    conn.fetchrow.return_value = {
        "channel_id": "chan1",
        "generation": 4,
        "attempt_count": 2,
    }

    job = await StreamSchedulePublishRepository(pool).claim_due_job()

    assert job is not None
    assert (job.channel_id, job.generation, job.attempt_count) == ("chan1", 4, 2)
    query = conn.fetchrow.await_args.args[0]
    assert "FOR UPDATE SKIP LOCKED" in query
    assert "locked_at" in query


async def test_enqueue_resets_retry_state_for_immediate_work() -> None:
    pool, conn = _pool()

    await StreamSchedulePublishRepository(pool).enqueue("chan1")

    query, *args = conn.execute.await_args.args
    assert "available_at = NOW()" in query
    assert "attempt_count = 0" in query
    assert args == ["chan1"]


async def test_complete_job_deletes_only_claimed_generation_and_unlocks_newer_work() -> None:
    pool, conn = _pool()
    conn.execute.side_effect = ["DELETE 0", "UPDATE 1"]
    repo = StreamSchedulePublishRepository(pool)

    await repo.complete_job("chan1", generation=4)

    delete = conn.execute.await_args_list[0]
    assert "generation = $2" in delete.args[0]
    assert delete.args[1:] == ("chan1", 4)
    unlock = conn.execute.await_args_list[1]
    assert "locked_at = NULL" in unlock.args[0]


async def test_failed_retry_is_bounded_and_keeps_sanitized_error_code() -> None:
    pool, conn = _pool()
    repo = StreamSchedulePublishRepository(pool)

    await repo.fail_job(
        "chan1",
        generation=4,
        attempt_count=7,
        error_code="provider_unavailable",
        retryable=True,
    )

    query, *args = conn.execute.await_args.args
    assert "LEAST" in query
    assert args[:4] == ["chan1", 4, "provider_unavailable", 7]


async def test_deferred_occurrence_requeue_never_delays_newer_immediate_work() -> None:
    pool, conn = _pool()

    await StreamSchedulePublishRepository(pool).enqueue_deferred("chan1", delay_seconds=3600)

    query, *args = conn.execute.await_args.args
    assert "LEAST(" in query
    assert "stream_schedule_publish_queue.available_at, EXCLUDED.available_at" in query
    assert "generation = stream_schedule_publish_queue.generation + 1" in query
    assert "locked_at = NULL" not in query
    assert args == ["chan1", 3600]


async def test_publish_overview_distinguishes_pending_error_and_synced() -> None:
    pool, conn = _pool()
    conn.fetchrow.return_value = {
        "pending_count": 1,
        "synced_count": 2,
        "blocked_count": 0,
        "error_count": 1,
        "last_error_code": "provider_unavailable",
        "last_synced_at": datetime(2026, 9, 29, 1, 0, tzinfo=UTC),
        "queued": True,
    }

    result = await StreamSchedulePublishRepository(pool).get_overview("chan1")

    query = conn.fetchrow.await_args.args[0]
    assert "stream_schedule_twitch_occurrences" in query
    assert "state.status IN ('pending', 'deferred')" in query
    assert result.status == "error"
    assert result.synced_count == 2
    assert result.pending_count == 1
    assert result.last_error_code == "provider_unavailable"


async def test_state_crud_maps_rows_and_keeps_queries_tenant_scoped() -> None:
    pool, conn = _pool()
    now = datetime(2026, 9, 29, 1, 0, tzinfo=UTC)
    conn.fetch.return_value = [
        {
            "id": 1,
            "channel_id": "chan1",
            "schedule_id": 7,
            "twitch_segment_id": "remote-1",
            "schedule_kind": "recurring",
            "identity_key": "weekly",
            "payload_fingerprint": "hash",
            "status": "synced",
            "error_code": None,
            "attempt_count": 0,
            "last_attempted_at": now,
            "synced_at": now,
        }
    ]
    repo = StreamSchedulePublishRepository(pool)

    states = await repo.list_states("chan1")
    await repo.mark_state_synced(
        "chan1",
        schedule_id=7,
        schedule_kind=ScheduleKind.RECURRING,
        twitch_segment_id="remote-1",
        identity_key="weekly",
        payload_fingerprint="hash",
    )
    await repo.mark_state_error(
        "chan1",
        schedule_id=7,
        schedule_kind=ScheduleKind.RECURRING,
        error_code="invalid_request",
        blocked=True,
    )
    await repo.mark_existing_state_error("chan1", 1, error_code="unauthorized", blocked=True)
    await repo.delete_state("chan1", 1)

    assert states[0].schedule_kind is ScheduleKind.RECURRING
    assert states[0].twitch_segment_id == "remote-1"
    assert conn.execute.await_args_list[0].args[1:] == (
        "chan1",
        7,
        "remote-1",
        "recurring",
        "weekly",
        "hash",
    )
    assert conn.execute.await_args_list[1].args[4] == "blocked"
    assert conn.execute.await_args_list[2].args[1:] == (
        "chan1",
        1,
        "blocked",
        "unauthorized",
    )
    assert conn.execute.await_args_list[3].args[1:] == ("chan1", 1)


async def test_occurrence_crud_maps_desired_and_status_state() -> None:
    pool, conn = _pool()
    occurrence_date = date(2026, 10, 1)
    row = {
        "id": 2,
        "channel_id": "chan1",
        "recurring_schedule_id": 7,
        "occurrence_date": occurrence_date,
        "twitch_segment_id": None,
        "desired_state": "cancelled",
        "status": "pending",
        "error_code": None,
        "last_attempted_at": None,
        "synced_at": None,
    }
    conn.fetch.return_value = [row]
    conn.fetchrow.return_value = row
    repo = StreamSchedulePublishRepository(pool)

    listed = await repo.list_occurrence_states("chan1")
    upserted = await repo.upsert_occurrence_desired(
        "chan1",
        recurring_schedule_id=7,
        occurrence_date=occurrence_date,
        desired_state="cancelled",
    )
    await repo.mark_occurrence_status(
        "chan1",
        2,
        status="synced",
        twitch_segment_id="occurrence-1",
    )
    await repo.delete_occurrence_state("chan1", 2)

    assert listed == [upserted]
    assert upserted.desired_state == "cancelled"
    assert conn.execute.await_args_list[0].args[1:] == (
        "chan1",
        2,
        "occurrence-1",
        "synced",
        None,
    )
    assert conn.execute.await_args_list[1].args[1:] == ("chan1", 2)


async def test_overview_status_precedence_covers_blocked_pending_synced_and_idle() -> None:
    pool, conn = _pool()
    repo = StreamSchedulePublishRepository(pool)
    rows = [
        {"queued": True, "queue_error_code": "internal_error"},
        {"blocked_count": 1},
        {"pending_count": 1},
        {"queued": True},
        {"synced_count": 1},
        {},
    ]
    conn.fetchrow.side_effect = rows

    results = [await repo.get_overview("chan1") for _ in rows]

    assert [item.status for item in results] == [
        "error",
        "blocked",
        "pending",
        "pending",
        "synced",
        "idle",
    ]
    assert results[0].last_error_code == "internal_error"
    assert results[0].error_count == 1
