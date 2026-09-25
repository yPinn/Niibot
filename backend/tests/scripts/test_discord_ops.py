"""Tests for Discord command-management scope safety."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from scripts.discord_ops.commands import _Runner


@pytest.mark.asyncio
@pytest.mark.parametrize("guild_id", [None, "123"])
async def test_remove_clears_only_the_selected_scope(guild_id: str | None) -> None:
    guild = object() if guild_id else None
    command = SimpleNamespace(name="ping", id="1")
    tree = SimpleNamespace(clear_commands=Mock(), sync=AsyncMock())
    runner = SimpleNamespace(
        guild_id=guild_id,
        tree=tree,
        _fetch=AsyncMock(return_value=([command], [command] if guild else [])),
        _guild_obj=Mock(return_value=guild),
        _display=Mock(),
    )

    await _Runner._rm(runner)

    tree.clear_commands.assert_called_once_with(guild=guild)
    tree.sync.assert_awaited_once_with(**({"guild": guild} if guild else {}))
