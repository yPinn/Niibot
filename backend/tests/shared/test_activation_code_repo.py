"""Unit tests for shared.repositories.activation_code — ActivationCodeRepository."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.repositories.activation_code import ActivationCodeRepository, _hash_code


def _make_pool(*, fetchrow=None, fetch=None, execute="UPDATE 1") -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    conn.fetchrow.return_value = fetchrow
    conn.fetch.return_value = fetch or []
    conn.execute.return_value = execute

    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=None)
    mock_tx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=mock_tx)

    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def _row(**values) -> MagicMock:
    row = MagicMock()
    row.__getitem__ = lambda _self, k: values[k]
    return row


# ---------------------------------------------------------------------------
# create_channel_points_grant
# ---------------------------------------------------------------------------


class TestCreateChannelPointsGrant:
    @pytest.mark.asyncio
    async def test_returns_6_digit_code(self):
        pool, _ = _make_pool()
        repo = ActivationCodeRepository(pool)
        code = await repo.create_channel_points_grant("u1")
        assert code.isdigit() and 100000 <= int(code) <= 999999

    @pytest.mark.asyncio
    async def test_revokes_prior_then_inserts(self):
        pool, conn = _make_pool()
        repo = ActivationCodeRepository(pool)
        await repo.create_channel_points_grant("u1")
        assert conn.execute.await_count == 2
        revoke_sql = conn.execute.await_args_list[0].args[0]
        insert_sql = conn.execute.await_args_list[1].args[0]
        assert "status = 'revoked'" in revoke_sql
        assert "INSERT INTO activation_codes" in insert_sql

    @pytest.mark.asyncio
    async def test_stores_hash_plain_and_provenance(self):
        pool, conn = _make_pool()
        repo = ActivationCodeRepository(pool)
        with patch("shared.repositories.activation_code._generate_otp", return_value="123456"):
            await repo.create_channel_points_grant(
                "u1", redemption_id="r1", channel_id="c1", reward_cost=500
            )
        args = conn.execute.await_args_list[1].args
        assert args[1] == _hash_code("123456")  # code_hash
        assert args[2] == "123456"  # code_plain
        assert args[6] == "r1" and args[7] == "c1" and args[8] == 500


class TestCreateOwnerCode:
    @pytest.mark.asyncio
    async def test_single_insert_unbound(self):
        pool, conn = _make_pool()
        repo = ActivationCodeRepository(pool)
        code = await repo.create_owner_code(issued_by_user_id="owner-uuid")
        assert code.isdigit()
        assert conn.execute.await_count == 1
        sql = conn.execute.await_args_list[0].args[0]
        assert "'owner_manual'" in sql and "NULL" in sql

    @pytest.mark.asyncio
    async def test_create_shim_delegates_to_channel_points(self):
        pool, conn = _make_pool()
        repo = ActivationCodeRepository(pool)
        await repo.create("twitch", "u1")
        assert "'channel_points'" in conn.execute.await_args_list[1].args[0]


# ---------------------------------------------------------------------------
# get_plain_code / find_unconsumed_grant
# ---------------------------------------------------------------------------


class TestReads:
    @pytest.mark.asyncio
    async def test_get_plain_code_found(self):
        pool, _ = _make_pool(fetchrow=_row(code_plain="123456"))
        repo = ActivationCodeRepository(pool)
        assert await repo.get_plain_code("twitch", "u1") == "123456"

    @pytest.mark.asyncio
    async def test_get_plain_code_none(self):
        pool, _ = _make_pool(fetchrow=None)
        repo = ActivationCodeRepository(pool)
        assert await repo.get_plain_code("twitch", "u1") is None

    @pytest.mark.asyncio
    async def test_find_unconsumed_grant_returns_row(self):
        grant = _row(id=7, code_hash="h", redemption_id="r", channel_id="c", reward_cost=1)
        pool, conn = _make_pool(fetchrow=grant)
        repo = ActivationCodeRepository(pool)
        result = await repo.find_unconsumed_grant("twitch", "u1")
        assert result is grant
        sql = conn.fetchrow.await_args_list[0].args[0]
        assert "kind = 'channel_points'" in sql and "status = 'issued'" in sql

    @pytest.mark.asyncio
    async def test_find_unconsumed_grant_none(self):
        pool, _ = _make_pool(fetchrow=None)
        repo = ActivationCodeRepository(pool)
        assert await repo.find_unconsumed_grant("twitch", "u1") is None


# ---------------------------------------------------------------------------
# consume
# ---------------------------------------------------------------------------


class TestConsume:
    @pytest.mark.asyncio
    async def test_uses_supplied_conn_without_acquiring(self):
        pool, pool_conn = _make_pool()
        ext = AsyncMock()
        repo = ActivationCodeRepository(pool)
        await repo.consume(9, "user-uuid", conn=ext)
        ext.execute.assert_awaited_once()
        pool.acquire.assert_not_called()
        sql = ext.execute.await_args_list[0].args[0]
        assert "status = 'consumed'" in sql and "status = 'issued'" in sql
        assert "code_plain = NULL" in sql

    @pytest.mark.asyncio
    async def test_acquires_when_no_conn(self):
        pool, conn = _make_pool()
        repo = ActivationCodeRepository(pool)
        await repo.consume(9, "user-uuid")
        conn.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# redeem
# ---------------------------------------------------------------------------


class TestRedeem:
    @pytest.mark.asyncio
    async def test_valid_unbound_code(self):
        pool, conn = _make_pool(fetchrow=_row(id=3, platform_user_id=None))
        repo = ActivationCodeRepository(pool)
        assert await repo.redeem("123456", "twitch", "u1", "user-uuid") is True
        consume_sql = conn.execute.await_args_list[-1].args[0]
        assert "status = 'consumed'" in consume_sql

    @pytest.mark.asyncio
    async def test_valid_code_bound_to_caller(self):
        pool, conn = _make_pool(fetchrow=_row(id=3, platform_user_id="u1"))
        repo = ActivationCodeRepository(pool)
        assert await repo.redeem("123456", "twitch", "u1", "user-uuid") is True

    @pytest.mark.asyncio
    async def test_code_bound_to_other_identity_bumps_attempts(self):
        pool, conn = _make_pool(fetchrow=_row(id=3, platform_user_id="someone-else"))
        repo = ActivationCodeRepository(pool)
        assert await repo.redeem("123456", "twitch", "u1", "user-uuid") is False
        bump_sql = conn.execute.await_args_list[-1].args[0]
        assert "attempt_count = attempt_count + 1" in bump_sql

    @pytest.mark.asyncio
    async def test_no_matching_code(self):
        pool, _ = _make_pool(fetchrow=None)
        repo = ActivationCodeRepository(pool)
        assert await repo.redeem("000000", "twitch", "u1", "user-uuid") is False

    @pytest.mark.asyncio
    async def test_supplied_conn_skips_own_transaction(self):
        ext = AsyncMock()
        ext.fetchrow.return_value = _row(id=3, platform_user_id=None)
        pool, _ = _make_pool()
        repo = ActivationCodeRepository(pool)
        assert await repo.redeem("123456", "twitch", "u1", "uid", conn=ext) is True
        pool.acquire.assert_not_called()


# ---------------------------------------------------------------------------
# revoke / invalidate / housekeeping
# ---------------------------------------------------------------------------


class TestRevokeAndHousekeeping:
    @pytest.mark.asyncio
    async def test_revoke_true_when_updated(self):
        pool, _ = _make_pool(execute="UPDATE 1")
        repo = ActivationCodeRepository(pool)
        assert await repo.revoke(5) is True

    @pytest.mark.asyncio
    async def test_revoke_false_when_noop(self):
        pool, _ = _make_pool(execute="UPDATE 0")
        repo = ActivationCodeRepository(pool)
        assert await repo.revoke(5) is False

    @pytest.mark.asyncio
    async def test_invalidate_false_when_noop(self):
        pool, _ = _make_pool(execute="UPDATE 0")
        repo = ActivationCodeRepository(pool)
        assert await repo.invalidate("twitch", "u1") is False

    @pytest.mark.asyncio
    async def test_mark_expired_returns_count(self):
        pool, _ = _make_pool(execute="UPDATE 4")
        repo = ActivationCodeRepository(pool)
        assert await repo.mark_expired() == 4

    @pytest.mark.asyncio
    async def test_scrub_terminal_returns_count(self):
        pool, _ = _make_pool(execute="DELETE 12")
        repo = ActivationCodeRepository(pool)
        assert await repo.scrub_terminal(90) == 12
