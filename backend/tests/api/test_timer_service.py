"""Unit tests for api.services.timer_service.TimerService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest
from api.services.timer_service import TimerService

pytestmark = pytest.mark.asyncio


class TestTimerServiceAliasConflict:
    async def test_duplicate_alias_raises_value_error_not_raw_db_error(self):
        """timers_channel_alias_unique (channel_id, command_alias) is a
        separate constraint from upsert()'s ON CONFLICT (channel_id,
        timer_name) target, so a duplicate alias reaches repo.upsert() as a
        raw UniqueViolationError. The router only knows how to turn a
        ValueError into a clean 400 (TimerInvalidError) — this must not
        bubble as an unhandled 500."""
        service = TimerService(pool=MagicMock())
        err = asyncpg.exceptions.UniqueViolationError(
            'duplicate key value violates unique constraint "timers_channel_alias_unique"'
        )
        err.constraint_name = "timers_channel_alias_unique"
        service.repo.upsert = AsyncMock(side_effect=err)

        with pytest.raises(ValueError, match="raffle"):
            await service.create_timer(
                "ch1",
                "timer_b",
                interval_seconds=300,
                min_lines=5,
                message_template="hi",
                command_alias="raffle",
            )

    async def test_unrelated_unique_violation_still_propagates(self):
        service = TimerService(pool=MagicMock())
        err = asyncpg.exceptions.UniqueViolationError("duplicate key value violates constraint")
        err.constraint_name = "some_other_constraint"
        service.repo.upsert = AsyncMock(side_effect=err)

        with pytest.raises(asyncpg.exceptions.UniqueViolationError):
            await service.create_timer(
                "ch1",
                "timer_b",
                interval_seconds=300,
                min_lines=5,
                message_template="hi",
                command_alias="raffle",
            )
