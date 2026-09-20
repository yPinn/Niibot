"""All authenticated dashboard requests honor server-side session revocation."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core.dependencies import get_active_session_payload

_USER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _pool(*, database_version: int | None) -> AsyncMock:
    pool = AsyncMock()
    pool.fetchval.return_value = database_version
    return pool


@pytest.mark.asyncio
async def test_current_session_version_is_accepted() -> None:
    payload = await get_active_session_payload(
        payload={"sub": _USER_ID, "sv": 3},
        pool=_pool(database_version=3),
    )

    assert payload["sub"] == _USER_ID


@pytest.mark.asyncio
async def test_incremented_database_version_invalidates_old_jwt() -> None:
    with pytest.raises(HTTPException) as error:
        await get_active_session_payload(
            payload={"sub": _USER_ID, "sv": 3},
            pool=_pool(database_version=4),
        )
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_missing_user_fails_closed() -> None:
    with pytest.raises(HTTPException) as error:
        await get_active_session_payload(
            payload={"sub": _USER_ID, "sv": 1},
            pool=_pool(database_version=None),
        )
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_legacy_jwt_without_session_version_is_version_one_during_rollout() -> None:
    payload = await get_active_session_payload(
        payload={"sub": _USER_ID},
        pool=_pool(database_version=1),
    )

    assert payload["sub"] == _USER_ID


@pytest.mark.asyncio
async def test_boolean_session_version_claim_is_rejected() -> None:
    with pytest.raises(HTTPException) as error:
        await get_active_session_payload(
            payload={"sub": _USER_ID, "sv": True},
            pool=_pool(database_version=1),
        )
    assert error.value.status_code == 401
