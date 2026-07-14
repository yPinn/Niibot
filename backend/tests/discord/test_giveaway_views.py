"""Unit tests for discord.cogs.giveaway._views.GiveawayView.

Covers the persistent-view timeout fix: GiveawayView is registered via
bot.add_view(view, message_id=...) for persistence across restarts, which
requires timeout=None. A bounded timeout would get silently torn down after
any gap in button clicks longer than the window, permanently breaking the
buttons until the bot restarts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord.cogs.giveaway._views import GiveawayView


def _make_view(end_time: datetime | None) -> GiveawayView:
    cog = MagicMock()
    cog.config = {
        "messages": {
            "no_participants": "沒人參加",
            "giveaway_ended": "抽獎已結束",
            "joined_success": "已參加",
        },
        "colors": {"active": "#5865F2", "ended": "#57F287"},
    }
    cog.remove_active_giveaway = AsyncMock()
    cog.update_participants = AsyncMock()
    return GiveawayView(
        host_id=123,
        prize_name="Steam Key",
        prize_count=1,
        giveaway_cog=cog,
        host_avatar_url="https://example.com/avatar.png",
        end_time=end_time,
    )


def _make_end_interaction() -> MagicMock:
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.message.edit = AsyncMock()
    interaction.guild = None
    return interaction


class TestTimeout:
    def test_timeout_is_none_with_long_duration(self) -> None:
        """A multi-day giveaway must not get a bounded discord.py timeout."""
        end_time = datetime.now(UTC) + timedelta(days=3)
        view = _make_view(end_time)
        assert view.timeout is None

    def test_timeout_is_none_with_short_remaining_time(self) -> None:
        """Even a giveaway about to end must not get a bounded timeout —
        expiry is enforced via end_time inside the button callbacks."""
        end_time = datetime.now(UTC) + timedelta(seconds=5)
        view = _make_view(end_time)
        assert view.timeout is None

    def test_timeout_is_none_with_already_past_end_time(self) -> None:
        end_time = datetime.now(UTC) - timedelta(seconds=5)
        view = _make_view(end_time)
        assert view.timeout is None

    def test_timeout_is_none_for_manual_end_giveaway(self) -> None:
        view = _make_view(None)
        assert view.timeout is None


@pytest.mark.asyncio
class TestJoinButtonExpiry:
    async def test_join_rejected_after_end_time(self) -> None:
        end_time = datetime.now(UTC) - timedelta(seconds=1)
        view = _make_view(end_time)
        interaction = MagicMock()
        interaction.response.send_message = AsyncMock()

        await GiveawayView.join_button(view, interaction, MagicMock())

        interaction.response.send_message.assert_awaited_once()
        assert "已截止" in interaction.response.send_message.call_args[0][0]
        assert len(view.participants) == 0

    async def test_join_allowed_before_end_time(self) -> None:
        end_time = datetime.now(UTC) + timedelta(hours=1)
        view = _make_view(end_time)
        interaction = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.user.id = 999
        interaction.message = None
        view.giveaway_cog.update_participants = AsyncMock()

        await GiveawayView.join_button(view, interaction, MagicMock())

        assert 999 in view.participants


@pytest.mark.asyncio
class TestViewStoppedOnFinish:
    """A persistent view (timeout=None) never expires on its own, so each path
    that finishes a giveaway must explicitly stop() it — otherwise every
    giveaway ever created stays registered in discord.py's view store for the
    life of the bot process."""

    async def test_cancel_giveaway_stops_the_view(self) -> None:
        view = _make_view(None)
        interaction = _make_end_interaction()

        await view._cancel_giveaway(interaction)

        assert view.is_finished()

    async def test_end_giveaway_with_no_participants_stops_the_view(self) -> None:
        view = _make_view(None)
        interaction = _make_end_interaction()

        await view._end_giveaway(interaction)

        assert view.is_finished()

    async def test_end_giveaway_with_winner_stops_the_view(self) -> None:
        view = _make_view(None)
        view.participants.add(999)
        interaction = _make_end_interaction()

        await view._end_giveaway(interaction)

        assert view.is_finished()

    async def test_end_giveaway_already_ended_does_not_double_stop(self) -> None:
        """Calling _end_giveaway again after it already finished must not raise."""
        view = _make_view(None)
        view.is_ended = True
        interaction = _make_end_interaction()

        await view._end_giveaway(interaction)

        interaction.response.send_message.assert_awaited_once()
