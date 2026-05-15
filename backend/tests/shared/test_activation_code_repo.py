"""Unit tests for shared.repositories.activation_code — ActivationCodeRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.repositories.activation_code import ActivationCodeRepository, _hash_code

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)


def _make_pool(*, fetchrow=None, execute="DELETE 0") -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    conn.fetchrow.return_value = fetchrow
    conn.execute.return_value = execute

    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=None)
    mock_tx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=mock_tx)

    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


class TestCreate:
    @pytest.mark.asyncio
    async def test_returns_6_digit_code(self):
        pool, conn = _make_pool(execute="DELETE 1")
        repo = ActivationCodeRepository(pool)
        code = await repo.create("twitch", "u1")
        assert code.isdigit()
        assert 100000 <= int(code) <= 999999

    @pytest.mark.asyncio
    async def test_deletes_prior_code_then_inserts(self):
        pool, conn = _make_pool(execute="DELETE 1")
        repo = ActivationCodeRepository(pool)
        await repo.create("twitch", "u1")
        # Two execute calls: DELETE old + INSERT new
        assert conn.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_stores_hash_not_plaintext(self):
        pool, conn = _make_pool(execute="DELETE 1")
        repo = ActivationCodeRepository(pool)
        with patch("shared.repositories.activation_code._generate_otp", return_value="123456"):
            await repo.create("twitch", "u1")
        insert_call = conn.execute.await_args_list[1]
        args = insert_call.args
        # First positional arg after the SQL is code_hash; should not equal plain "123456"
        assert args[1] == _hash_code("123456")
        assert args[2] == "123456"  # code_plain stored separately


# ---------------------------------------------------------------------------
# get_plain_code
# ---------------------------------------------------------------------------


class TestGetPlainCode:
    @pytest.mark.asyncio
    async def test_returns_code_when_found(self):
        row = MagicMock()
        row.__getitem__ = MagicMock(side_effect=lambda k: "123456" if k == "code_plain" else None)
        pool, _ = _make_pool(fetchrow=row)
        repo = ActivationCodeRepository(pool)
        result = await repo.get_plain_code("twitch", "u1")
        assert result == "123456"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        pool, _ = _make_pool(fetchrow=None)
        repo = ActivationCodeRepository(pool)
        result = await repo.get_plain_code("twitch", "u1")
        assert result is None


# ---------------------------------------------------------------------------
# redeem
# ---------------------------------------------------------------------------


class TestRedeem:
    @pytest.mark.asyncio
    async def test_returns_true_on_valid_code(self):
        row = MagicMock()
        row.__getitem__ = MagicMock(return_value=_hash_code("123456"))
        pool, conn = _make_pool(fetchrow=row, execute="UPDATE 1")
        repo = ActivationCodeRepository(pool)
        result = await repo.redeem("123456", "twitch", "u1", "user-uuid")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_code_not_found(self):
        pool, _ = _make_pool(fetchrow=None)
        repo = ActivationCodeRepository(pool)
        result = await repo.redeem("000000", "twitch", "u1", "user-uuid")
        assert result is False

    @pytest.mark.asyncio
    async def test_marks_used_and_activates_user(self):
        row = MagicMock()
        pool, conn = _make_pool(fetchrow=row, execute="UPDATE 1")
        repo = ActivationCodeRepository(pool)
        await repo.redeem("123456", "twitch", "u1", "user-uuid")
        # Two execute calls: mark used + activate user
        assert conn.execute.await_count == 2


# ---------------------------------------------------------------------------
# invalidate
# ---------------------------------------------------------------------------


class TestInvalidate:
    @pytest.mark.asyncio
    async def test_returns_true_when_row_deleted(self):
        pool, _ = _make_pool(execute="DELETE 1")
        repo = ActivationCodeRepository(pool)
        result = await repo.invalidate("twitch", "u1")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_row_deleted(self):
        pool, _ = _make_pool(execute="DELETE 0")
        repo = ActivationCodeRepository(pool)
        result = await repo.invalidate("twitch", "u1")
        assert result is False
