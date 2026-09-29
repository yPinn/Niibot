"""Shared desired/active bot selection persistence contracts."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.repositories.bot_selection import BotSelectionRepository
from shared.twitch_scopes import BOT_SCOPES


def _pool_with(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


def _tx_cm() -> MagicMock:
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=None)
    return tx


def _row(**overrides):
    row = {
        "channel_id": "channel-a",
        "desired_bot_user_id": "bot-b",
        "active_bot_user_id": None,
        "selection_version": 1,
        "acked_version": 0,
        "status": "switching",
        "last_error_code": None,
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_request_serializes_channel_rechecks_candidate_and_notifies_without_secrets():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_tx_cm())
    conn.fetchval.return_value = True
    conn.fetchrow.return_value = _row()
    repository = BotSelectionRepository(_pool_with(conn))

    result = await repository.request(
        channel_id="channel-a",
        bot_user_id="bot-b",
        actor_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        system_bot_id="system-bot",
        required_scopes=set(BOT_SCOPES),
    )

    assert result is not None
    statements = [str(item.args[0]) for item in conn.execute.await_args_list]
    assert any("pg_advisory_xact_lock" in sql for sql in statements)
    assert any(
        "twitch-runtime-identity:bot-b" in str(item.args) for item in conn.execute.await_args_list
    )
    candidate_sql = conn.fetchval.await_args.args[0]
    assert "token_type = 'broadcaster'" in candidate_sql
    assert "NOT EXISTS" in candidate_sql
    assert any("tenant_audit_events" in sql for sql in statements)
    notify = next(item.args for item in conn.execute.await_args_list if "pg_notify" in item.args[0])
    assert notify[1] == "bot_selection_changed"
    assert "channel-a" in notify[2]
    assert "bot-b" not in notify[2]
    assert all("access" not in str(arg).lower() for arg in notify)


@pytest.mark.asyncio
async def test_request_returns_none_when_mapping_disappears_during_preflight():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_tx_cm())
    conn.fetchval.return_value = False
    repository = BotSelectionRepository(_pool_with(conn))

    result = await repository.request(
        channel_id="channel-a",
        bot_user_id="bot-b",
        actor_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        system_bot_id="system-bot",
        required_scopes=set(BOT_SCOPES),
    )

    assert result is None
    conn.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
async def test_selecting_current_active_sender_is_idempotent():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_tx_cm())
    conn.fetchval.return_value = True
    conn.fetchrow.return_value = _row(
        desired_bot_user_id="bot-b",
        active_bot_user_id="bot-b",
        selection_version=4,
        acked_version=4,
        status="active",
    )
    repository = BotSelectionRepository(_pool_with(conn))

    result = await repository.request(
        channel_id="channel-a",
        bot_user_id="bot-b",
        actor_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        system_bot_id="system-bot",
        required_scopes=set(BOT_SCOPES),
    )

    assert result is not None
    assert result.selection_version == 4
    assert not any("pg_notify" in str(item.args[0]) for item in conn.execute.await_args_list)


@pytest.mark.asyncio
async def test_runtime_ack_is_version_guarded_against_a_newer_selection():
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    repository = BotSelectionRepository(_pool_with(conn))

    assert not await repository.mark_active(
        channel_id="channel-a",
        selection_version=2,
        bot_user_id="bot-b",
    )
    sql = conn.fetchrow.await_args.args[0]
    assert "selection_version = $2" in sql
    assert "status = 'switching'" in sql


@pytest.mark.asyncio
async def test_runtime_failure_keeps_active_sender_and_records_only_safe_error_code():
    conn = AsyncMock()
    conn.fetchrow.return_value = _row(
        desired_bot_user_id="bot-b",
        active_bot_user_id="bot-a",
        selection_version=3,
        acked_version=3,
        status="failed",
        last_error_code="bot_not_moderator",
    )
    repository = BotSelectionRepository(_pool_with(conn))

    assert await repository.mark_failed(
        channel_id="channel-a",
        selection_version=3,
        error_code="bot_not_moderator",
    )
    sql = conn.fetchrow.await_args.args[0]
    assert "active_bot_user_id" not in sql.split("WHERE", 1)[0]
