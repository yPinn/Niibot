"""Chat-based command management: !na, !ne, !nd.

Syntax:
    !na !指令名 [options] 回覆文字
    !ne !指令名 [options] [新回覆文字]
    !nd !指令名

Options:
    -cd=N          Cooldown in seconds
    -role=X        Min role: everyone/sub/vip/mod/broadcaster
    -alias=a,b,c   Comma-separated aliases

Variables in response:
    $(user)    Chatter display name
    $(query)   Remaining text after the command

Examples:
    !na !你好 $(user) 你好呀！
    !na !問候 -cd=30 -alias=greeting,hey $(user) 嗨！
    !na !ask !ai $(query)
    !ne !問候 -cd=60
    !ne !問候 新的回覆文字
    !nd !問候
"""

import logging
import re
from typing import TYPE_CHECKING

from twitchio.ext import commands

from shared.repositories.command_config import CommandConfigRepository

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER = logging.getLogger("CommandManagerComponent")

# Mapping short role names to DB values
ROLE_ALIASES = {
    "everyone": "everyone",
    "all": "everyone",
    "sub": "subscriber",
    "subscriber": "subscriber",
    "vip": "vip",
    "mod": "moderator",
    "moderator": "moderator",
    "broadcaster": "broadcaster",
    "owner": "broadcaster",
}

# Pattern to match option flags like -cd=30, -alias=a,b
_OPT_PATTERN = re.compile(r"-(\w+)=(\S+)")


def _parse_args(raw: str) -> tuple[dict[str, str], str]:
    """Parse option flags and remaining text from raw arguments.

    Returns (options_dict, remaining_text).
    """
    options: dict[str, str] = {}
    remaining_parts: list[str] = []

    for token in raw.split():
        match = _OPT_PATTERN.fullmatch(token)
        if match:
            options[match.group(1).lower()] = match.group(2)
        else:
            remaining_parts.append(token)

    return options, " ".join(remaining_parts)


class CommandManagerComponent(commands.Component):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self.cmd_repo = CommandConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]
        LOGGER.info("CommandManager component initialized")

    @commands.command(name="na")
    async def na(self, ctx: commands.Context["Bot"], *, args: str | None = None) -> None:
        """Add a custom command. Moderator+ only."""
        if not ctx.chatter.moderator and not ctx.chatter.broadcaster:  # type: ignore[attr-defined]
            return

        if not args or not args.strip():
            await ctx.reply("用法: !na !指令名 [-cd=N] [-alias=a,b] 回覆文字")
            return

        parts = args.strip().split(maxsplit=1)
        cmd_name = parts[0].lstrip("!").lower()
        remaining = parts[1] if len(parts) > 1 else ""

        if not cmd_name:
            await ctx.reply("用法: !na !指令名 回覆文字")
            return

        # Check if command already exists
        channel_id = str(ctx.channel.id)
        existing = await self.cmd_repo.get_config(channel_id, cmd_name)
        if existing:
            await ctx.reply(f"指令 !{cmd_name} 已存在，請使用 !ne 修改")
            return

        # Parse options and response text
        options, response_text = _parse_args(remaining)

        if not response_text:
            await ctx.reply("請提供回覆文字: !na !指令名 回覆文字")
            return

        # Build config from options
        cooldown = int(options["cd"]) if "cd" in options else None
        role_input = options.get("role", "everyone")
        min_role = ROLE_ALIASES.get(role_input.lower(), "everyone")
        aliases = options.get("alias")

        config = await self.cmd_repo.upsert_config(
            channel_id,
            cmd_name,
            command_type="custom",
            enabled=True,
            custom_response=response_text,
            cooldown=cooldown,
            min_role=min_role,
            aliases=aliases,
        )

        alias_info = f" (別名: {config.aliases})" if config.aliases else ""
        await ctx.reply(f"已新增指令 !{cmd_name}{alias_info}")
        LOGGER.info(f"Command added: !{cmd_name} by {ctx.chatter.name}")

    @commands.command(name="ne")
    async def ne(self, ctx: commands.Context["Bot"], *, args: str | None = None) -> None:
        """Edit a custom command. Moderator+ only."""
        if not ctx.chatter.moderator and not ctx.chatter.broadcaster:  # type: ignore[attr-defined]
            return

        if not args or not args.strip():
            await ctx.reply("用法: !ne !指令名 [-cd=N] [-alias=a,b] [新回覆文字]")
            return

        parts = args.strip().split(maxsplit=1)
        cmd_name = parts[0].lstrip("!").lower()
        remaining = parts[1] if len(parts) > 1 else ""

        if not cmd_name:
            await ctx.reply("用法: !ne !指令名 [選項] [新回覆文字]")
            return

        channel_id = str(ctx.channel.id)
        existing = await self.cmd_repo.get_config(channel_id, cmd_name)
        if not existing or existing.command_type != "custom":
            await ctx.reply(f"找不到自訂指令 !{cmd_name}")
            return

        options, response_text = _parse_args(remaining)

        # Build update kwargs (only include provided values)
        kwargs: dict = {}
        if "cd" in options:
            kwargs["cooldown"] = int(options["cd"])
        if "role" in options:
            kwargs["min_role"] = ROLE_ALIASES.get(options["role"].lower(), "everyone")
        if "alias" in options:
            kwargs["aliases"] = options["alias"]
        if response_text:
            kwargs["custom_response"] = response_text

        if not kwargs:
            await ctx.reply("請提供要修改的內容: !ne !指令名 [-cd=N] [新回覆文字]")
            return

        config = await self.cmd_repo.upsert_config(
            channel_id,
            cmd_name,
            command_type="custom",
            **kwargs,
        )

        changes = []
        if response_text:
            changes.append("回覆")
        if "cd" in options:
            changes.append(f"冷卻={config.cooldown}s")
        if "role" in options:
            changes.append(f"權限={config.min_role}")
        if "alias" in options:
            changes.append(f"別名={config.aliases}")

        await ctx.reply(f"已更新 !{cmd_name}：{', '.join(changes)}")
        LOGGER.info(f"Command edited: !{cmd_name} by {ctx.chatter.name}")

    @commands.command(name="nd")
    async def nd(self, ctx: commands.Context["Bot"], *, args: str | None = None) -> None:
        """Delete a custom command. Moderator+ only."""
        if not ctx.chatter.moderator and not ctx.chatter.broadcaster:  # type: ignore[attr-defined]
            return

        if not args or not args.strip():
            await ctx.reply("用法: !nd !指令名")
            return

        cmd_name = args.strip().lstrip("!").lower()
        if not cmd_name:
            await ctx.reply("用法: !nd !指令名")
            return

        channel_id = str(ctx.channel.id)
        deleted = await self.cmd_repo.delete_config(channel_id, cmd_name)

        if deleted:
            await ctx.reply(f"已刪除指令 !{cmd_name}")
            LOGGER.info(f"Command deleted: !{cmd_name} by {ctx.chatter.name}")
        else:
            await ctx.reply(f"找不到自訂指令 !{cmd_name}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(CommandManagerComponent(bot))
    LOGGER.info("CommandManager component loaded")


async def teardown(bot: commands.Bot) -> None:
    LOGGER.info("CommandManager component unloaded")
