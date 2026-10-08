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
        _warn_other_scope=AsyncMock(),
    )

    await _Runner._sync(runner)

    assert tree.sync.await_count == writes
    runner._warn_other_scope.assert_awaited_once()  # checked even when the write is skipped


def _cmd(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


def _guilds(*guilds: SimpleNamespace):
    async def fetch_guilds(limit: int | None = None):
        for g in guilds:
            yield g

    return fetch_guilds


@pytest.mark.asyncio
async def test_guild_sync_warns_about_stale_global_commands(capsys) -> None:
    runner = SimpleNamespace(
        guild_id="123",
        env="stg",
        tree=SimpleNamespace(fetch_commands=AsyncMock(return_value=[_cmd("codex"), _cmd("ai")])),
    )

    await _Runner._warn_other_scope(runner)

    out = capsys.readouterr().out
    assert out.startswith("::warning title=Stale Discord commands::global still has 2 command(s)")
    assert "(/ai, /codex)" in out
    assert "npm run nb -- discord rm --env stg --global" in out


@pytest.mark.asyncio
async def test_global_sync_scans_guilds_and_skips_unreadable_ones(capsys) -> None:
    import discord

    async def fetch_commands(guild=None):
        if guild.id == 2:
            raise discord.HTTPException(SimpleNamespace(status=403, reason="Forbidden"), "no scope")
        return [_cmd("codex")] if guild.id == 1 else []

    runner = SimpleNamespace(
        guild_id=None,
        env="prod",
        tree=SimpleNamespace(fetch_commands=fetch_commands),
        fetch_guilds=_guilds(
            SimpleNamespace(id=1, name="Main"),
            SimpleNamespace(id=2, name="NoScope"),
            SimpleNamespace(id=3, name="Clean"),
        ),
    )

    await _Runner._warn_other_scope(runner)

    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1
    assert "guild 1 (Main) still has 1 command(s) outside this sync (/codex)" in lines[0]
    assert lines[0].endswith("npm run nb -- discord rm --env prod --guild 1")


@pytest.mark.asyncio
async def test_clean_other_scope_reports_nothing_stale(capsys) -> None:
    runner = SimpleNamespace(
        guild_id=None,
        env="prod",
        tree=SimpleNamespace(fetch_commands=AsyncMock(return_value=[])),
        fetch_guilds=_guilds(SimpleNamespace(id=1, name="Main")),
    )

    await _Runner._warn_other_scope(runner)

    assert capsys.readouterr().out == "No stale commands in the other scope.\n"


@pytest.mark.parametrize("action", ["ls", "diff", "sync", "rm"])
def test_every_action_accepts_global(action: str) -> None:
    """nb forwards --global to any action, so each parser must accept it."""
    from scripts.discord_ops.commands import _build_parser

    args = _build_parser().parse_args([action, "--env", "prod", "--global"])
    assert args.force_global is True
