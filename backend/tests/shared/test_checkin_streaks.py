"""Contracts for rebuilding the active check-in streak projection."""

from unittest.mock import AsyncMock

import pytest

from shared.checkin_streaks import rebuild_checkin_streaks


@pytest.mark.asyncio
async def test_rebuild_uses_broadcast_day_ordinals_for_live_only_channels() -> None:
    conn = AsyncMock()

    await rebuild_checkin_streaks(conn, "ch1")

    assert conn.execute.await_count == 2
    delete_sql, delete_channel = conn.execute.await_args_list[0].args
    assert "DELETE FROM viewer_daily_checkin_streaks" in delete_sql
    assert delete_channel == "ch1"

    rebuild_sql, rebuild_channel = conn.execute.await_args_list[1].args
    normalized_sql = " ".join(rebuild_sql.split())
    assert "checkin_settings" in normalized_sql
    assert "live_only" in normalized_sql
    assert "checkin_eligible" in normalized_sql
    assert "DENSE_RANK() OVER (ORDER BY checkin_broadcast_day)" in normalized_sql
    assert "NOT settings.live_only OR eligible_days.day_ordinal IS NOT NULL" in normalized_sql
    assert rebuild_channel == "ch1"
