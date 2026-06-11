"""Tests for services.identity_service.IdentityService.

Covers the four branches of find_or_link:
  1. fast path                — existing identity returned, last_seen_at touched
  2. account-link path        — link_to_user_id given, identity inserted
  3. reconciliation path      — identity missing but channels.owner_user_id rescues
  4. fresh signup             — brand-new user + identity

Plus the UniqueViolationError race-condition handlers.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from api.services.identity_service import IdentityService
from asyncpg.exceptions import UniqueViolationError


def _pool_with(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


def _tx_cm() -> MagicMock:
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=None)  # propagate exceptions
    return tx


def _identity_row(
    user_id: str | uuid.UUID,
    *,
    identity_id: str | uuid.UUID | None = None,
    platform: str = "twitch",
    platform_user_id: str = "12345",
    username: str = "alice",
) -> MagicMock:
    """Build a fake asyncpg row matching IdentityRepository.find_by_platform_id."""
    identity_id = identity_id or uuid.uuid4()
    payload = {
        "id": str(identity_id),
        "user_id": str(user_id),
        "platform": platform,
        "platform_user_id": platform_user_id,
        "username": username,
        "linked_at": "2026-01-01T00:00:00+00:00",
        "last_seen_at": "2026-01-01T00:00:00+00:00",
    }
    row = MagicMock()
    row.__getitem__ = lambda self, k: payload[k]
    row.keys = MagicMock(return_value=payload.keys())
    # asyncpg rows behave like dict(row)
    row.items = lambda: payload.items()
    return row


@pytest.mark.asyncio
class TestFindOrLinkFastPath:
    async def test_existing_identity_returns_user_id_and_touches_last_seen(self):
        existing_user = uuid.uuid4()
        conn = AsyncMock()
        # find_by_platform_id returns existing row
        conn.fetchrow.return_value = _identity_row(existing_user, username="alice")

        pool = _pool_with(conn)
        svc = IdentityService(pool)

        result = await svc.find_or_link(
            platform="twitch",
            platform_user_id="12345",
            username="alice",
        )

        assert result.user_id == str(existing_user)
        assert result.is_new_user is False
        assert result.is_new_identity is False
        assert result.was_reconciled is False
        # touch_last_seen + auth_events INSERT — both via execute
        assert conn.execute.await_count >= 1

    async def test_existing_identity_updates_username_if_changed(self):
        existing_user = uuid.uuid4()
        conn = AsyncMock()
        conn.fetchrow.return_value = _identity_row(existing_user, username="old_name")

        pool = _pool_with(conn)
        svc = IdentityService(pool)

        await svc.find_or_link(
            platform="twitch",
            platform_user_id="12345",
            username="new_name",
        )

        # Verify UPDATE username was issued among the execute calls
        executed_sqls = " ".join(call.args[0] for call in conn.execute.await_args_list)
        assert "UPDATE identities SET username" in executed_sqls


@pytest.mark.asyncio
class TestFindOrLinkAccountLink:
    async def test_link_to_existing_user_inserts_new_identity(self):
        target_user = uuid.uuid4()
        new_identity_id = uuid.uuid4()

        conn = AsyncMock()
        # find_by_platform_id → None (missing); insert_for_user RETURNING new row
        conn.fetchrow.side_effect = [
            None,  # initial find
            _identity_row(
                target_user, identity_id=new_identity_id, platform="discord"
            ),  # INSERT RETURNING
        ]
        conn.transaction = MagicMock(return_value=_tx_cm())

        pool = _pool_with(conn)
        svc = IdentityService(pool)

        result = await svc.find_or_link(
            platform="discord",
            platform_user_id="discord-999",
            username="alice-on-discord",
            link_to_user_id=str(target_user),
        )

        assert result.user_id == str(target_user)
        assert result.is_new_user is False
        assert result.is_new_identity is True
        assert result.was_reconciled is False

    async def test_link_race_returns_existing_row(self):
        target_user = uuid.uuid4()
        winner_user = uuid.uuid4()

        conn = AsyncMock()
        # initial find returns None; insert raises UniqueViolation; re-find returns winner
        conn.fetchrow.side_effect = [
            None,
            UniqueViolationError("dup"),  # INSERT fetchrow inside tx
            _identity_row(winner_user),  # re-read after race
        ]
        conn.transaction = MagicMock(return_value=_tx_cm())

        pool = _pool_with(conn)
        svc = IdentityService(pool)

        result = await svc.find_or_link(
            platform="discord",
            platform_user_id="discord-999",
            username="alice",
            link_to_user_id=str(target_user),
        )

        # Race loser still ends up with a valid identity
        assert result.user_id == str(winner_user)
        assert result.is_new_identity is False
        assert result.was_reconciled is False


@pytest.mark.asyncio
class TestFindOrLinkReconciliation:
    async def test_reconciles_via_channels_owner_user_id(self):
        recovered_user = uuid.uuid4()
        new_identity = uuid.uuid4()

        conn = AsyncMock()
        # Sequence: initial find None; channels lookup → recovered user; insert returns identity
        owner_row = MagicMock()
        owner_row.__getitem__ = lambda self, k: str(recovered_user) if k == "user_id" else None
        conn.fetchrow.side_effect = [
            None,  # find identity
            owner_row,  # channels lookup
            _identity_row(recovered_user, identity_id=new_identity),  # INSERT RETURNING
        ]
        conn.transaction = MagicMock(return_value=_tx_cm())

        pool = _pool_with(conn)
        svc = IdentityService(pool)

        result = await svc.find_or_link(
            platform="twitch",
            platform_user_id="55555",
            username="alice",
        )

        assert result.user_id == str(recovered_user)
        assert result.was_reconciled is True
        assert result.is_new_user is False
        assert result.is_new_identity is True


@pytest.mark.asyncio
class TestFindOrLinkFreshSignup:
    async def test_creates_new_user_and_identity(self):
        new_user = uuid.uuid4()
        new_identity = uuid.uuid4()

        conn = AsyncMock()
        owner_row = MagicMock()
        owner_row.__getitem__ = lambda self, k: None  # no channels owner
        user_row = MagicMock()
        user_row.__getitem__ = lambda self, k: str(new_user) if k == "id" else None

        conn.fetchrow.side_effect = [
            None,  # identity find
            None,  # channels lookup (no orphan)
            None,  # activation_codes lookup (no historic)
            user_row,  # INSERT INTO users RETURNING id
            _identity_row(new_user, identity_id=new_identity),  # identity INSERT RETURNING
        ]
        conn.transaction = MagicMock(return_value=_tx_cm())

        pool = _pool_with(conn)
        svc = IdentityService(pool)

        result = await svc.find_or_link(
            platform="twitch",
            platform_user_id="77777",
            username="newbie",
            display_name="Newbie",
        )

        assert result.user_id == str(new_user)
        assert result.is_new_user is True
        assert result.is_new_identity is True
        assert result.was_reconciled is False

    async def test_fresh_signup_race_returns_winner(self):
        new_user = uuid.uuid4()
        winner_user = uuid.uuid4()
        conn = AsyncMock()
        owner_row = MagicMock()
        owner_row.__getitem__ = lambda self, k: None
        user_row = MagicMock()
        user_row.__getitem__ = lambda self, k: str(new_user) if k == "id" else None

        conn.fetchrow.side_effect = [
            None,  # identity find
            None,  # channels lookup
            None,  # activation_codes
            user_row,  # INSERT users
            UniqueViolationError("dup"),  # INSERT identities — loser
            _identity_row(winner_user),  # re-read returns winner
        ]
        conn.transaction = MagicMock(return_value=_tx_cm())

        pool = _pool_with(conn)
        svc = IdentityService(pool)

        result = await svc.find_or_link(
            platform="twitch",
            platform_user_id="77777",
            username="newbie",
        )

        assert result.user_id == str(winner_user)
        assert result.is_new_user is False
        assert result.was_reconciled is False
