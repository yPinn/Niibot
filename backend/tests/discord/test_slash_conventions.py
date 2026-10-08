"""Slash-command conventions (core/slash.py, docs/guides/discord.md 指令慣例)."""

from __future__ import annotations

import discord
import pytest
from discord import app_commands

from cogs.birthday.cog import BirthdayCog
from cogs.codex_resets.cog import CodexResetsCog
from cogs.eat.cog import EatCog
from cogs.events.cog import EventsCog
from cogs.moderation import ModerationCog
from cogs.utility import UtilityCog
from core import GUILD_ONLY, guild_group

GUILD_GROUPS = [
    # (group, permissions that hide it — None = visible to everyone)
    (CodexResetsCog.config, discord.Permissions(manage_guild=True)),
    (EventsCog.log, discord.Permissions(manage_guild=True)),
    (ModerationCog.mod, discord.Permissions(manage_messages=True)),
    (BirthdayCog.bday_group, None),
    (EatCog.food_group, None),
    (UtilityCog.info, None),
]


@pytest.mark.parametrize(
    ("group", "permissions"), GUILD_GROUPS, ids=lambda v: getattr(v, "name", "")
)
def test_guild_groups_are_guild_only_with_expected_visibility(
    group: app_commands.Group, permissions: discord.Permissions | None
) -> None:
    assert group.guild_only  # legacy dm_permission=False
    assert group.allowed_contexts == GUILD_ONLY  # contexts=[0]
    assert group.default_permissions == permissions


@pytest.mark.parametrize("group", [CodexResetsCog.config, EventsCog.log], ids=lambda g: g.name)
def test_hidden_settings_groups_have_no_runtime_permission_check(group: app_commands.Group) -> None:
    """Hidden groups rely on Discord, so admins can re-grant them under Integrations."""
    for command in group.walk_commands():
        assert isinstance(command, app_commands.Command)
        assert not any("has_permissions" in repr(check) for check in command.checks), command.name


def test_guild_group_without_permissions_is_visible() -> None:
    group = guild_group("x", "y")
    assert group.default_permissions is None
    assert group.allowed_contexts is not None
    assert group.allowed_contexts.guild
    assert not group.allowed_contexts.dm_channel
    assert not group.allowed_contexts.private_channel
