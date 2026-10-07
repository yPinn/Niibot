"""Tests for Discord command-management scope safety."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from scripts.discord_ops.commands import _Runner, diff_commands


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


def _local(**overrides) -> dict:
    """Shape of discord.py's Command.to_dict(tree) for a guild-only slash group."""
    return {
        "name": "codex",
        "description": "Codex 重置通知",
        "type": 1,
        "options": [
            {
                "name": "watch",
                "description": "開關重置觀察通知",
                "type": 1,
                "options": [
                    {"type": 5, "name": "enabled", "description": "是否接收", "required": True}
                ],
            }
        ],
        "nsfw": False,
        "dm_permission": False,
        "default_member_permissions": None,
        "contexts": [0],
        "integration_types": None,
        **overrides,
    }


def _remote(**overrides) -> dict:
    """Shape of AppCommand.to_dict() plus the fields _remote_payload adds back."""
    return {
        "id": 99,
        "application_id": 1,
        "name": "codex",
        "description": "Codex 重置通知",
        "type": 1,
        "name_localizations": {},
        "description_localizations": {},
        "contexts": [0],
        "integration_types": [0],
        "options": [
            {
                "name": "watch",
                "description": "開關重置觀察通知",
                "type": 1,
                "name_localizations": {},
                "description_localizations": {},
                "options": [
                    {
                        "name": "enabled",
                        "description": "是否接收",
                        "type": 5,
                        "required": True,
                        "choices": [],
                        "channel_types": [],
                        "min_value": None,
                        "max_value": None,
                        "min_length": None,
                        "max_length": None,
                        "autocomplete": False,
                        "options": [],
                        "name_localizations": {},
                        "description_localizations": {},
                    }
                ],
            }
        ],
        "default_member_permissions": None,
        "nsfw": False,
        **overrides,
    }


class TestDiffCommands:
    def test_in_sync_payloads_compare_equal(self) -> None:
        assert diff_commands([_local()], [_remote()]) == ([], [], [])

    def test_new_and_removed_commands(self) -> None:
        added, removed, changed = diff_commands([_local()], [_remote(name="rate")])
        assert (added, removed, changed) == (["codex"], ["rate"], [])

    def test_changed_option_description_is_detected(self) -> None:
        local = _local()
        local["options"][0]["description"] = "新的說明"
        assert diff_commands([local], [_remote()]) == ([], [], ["codex"])

    def test_changed_permissions_are_detected(self) -> None:
        local = _local(default_member_permissions=8)
        assert diff_commands([local], [_remote()]) == ([], [], ["codex"])
        remote = _remote(default_member_permissions=8)
        assert diff_commands([local], [remote]) == ([], [], [])

    def test_server_defaulted_contexts_ignored_when_one_side_unset(self) -> None:
        assert diff_commands([_local(contexts=None)], [_remote(contexts=[0, 1, 2])]) == (
            [],
            [],
            [],
        )
        assert diff_commands([_local(contexts=[0, 1])], [_remote()]) == ([], [], ["codex"])

    def test_context_menu_keyed_separately_from_slash(self) -> None:
        menu = {"name": "codex", "type": 3, "nsfw": False}
        added, _, _ = diff_commands([_local(), menu], [_remote()])
        assert added == ["codex (type 3)"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("pending", "writes"), [(([], [], []), 0), ((["codex"], [], []), 1)])
async def test_sync_if_changed_skips_write_when_in_sync(pending, writes) -> None:
    tree = SimpleNamespace(sync=AsyncMock(return_value=[]), copy_global_to=Mock())
    runner = SimpleNamespace(
        guild_id=None,
        if_changed=True,
        tree=tree,
        _load_tree=AsyncMock(return_value=True),
        _compare=AsyncMock(return_value=pending),
        _guild_obj=Mock(return_value=None),
    )

    await _Runner._sync(runner)

    assert tree.sync.await_count == writes
