"""Slash-command conventions shared by every cog.

See docs/guides/discord.md (指令慣例):

- Anything that needs a guild (guild data, guild permissions, members) is
  guild-only — `contexts=[0]`, plus the legacy `dm_permission=False`.
- A group whose every subcommand is privileged is hidden with
  `default_member_permissions` and has no runtime permission check, so server
  admins can re-grant it under Server Settings → Integrations.
- A group mixing public and privileged subcommands cannot be hidden (Discord
  only applies permissions to the top-level command), so its privileged
  subcommands keep a runtime `app_commands.checks.has_permissions`.
"""

from __future__ import annotations

import discord
from discord import app_commands

GUILD_ONLY = app_commands.AppCommandContext(guild=True)


def guild_group(
    name: str, description: str, *, permissions: discord.Permissions | None = None
) -> app_commands.Group:
    """A guild-only command group; `permissions` hides it from members lacking them."""
    return app_commands.Group(
        name=name,
        description=description,
        guild_only=True,
        allowed_contexts=GUILD_ONLY,
        default_permissions=permissions,
    )
