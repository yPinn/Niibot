"""Chat-based command management: !cmd a/e/d.

Syntax:
    !cmd a !指令名 [options] 回覆文字
    !cmd e !指令名 [options] [新回覆文字]
    !cmd d !指令名

Options:
    -cd=N          Cooldown in seconds
    -role=X        Min role: everyone/sub/vip/mod/broadcaster
    -alias=a,b,c   Comma-separated aliases
    -enable=on/off Toggle command enabled state

Variables in response:
    $(user)             Chatter display name
    $(query)            Remaining text after the command
    $(channel)          Channel name
    $(random min,max)   Random integer in range [min, max]
    $(pick a,b,c)       Random pick from comma-separated items

Examples:
    !cmd a !你好 $(user) 你好呀！
    !cmd a !問候 -cd=30 -alias=greeting,hey $(user) 嗨！
    !cmd a !ask !ai $(query)
    !cmd e !問候 -cd=60
    !cmd e !問候 新的回覆文字
    !cmd d !問候
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


_TRUTHY = {"on", "true", "yes", "1"}
_FALSY = {"off", "false", "no", "0"}


def _parse_bool(value: str) -> bool | None:
    """Parse a boolean-ish string. Returns None if unrecognised."""
    if value.lower() in _TRUTHY:
        return True
    if value.lower() in _FALSY:
        return False
    return None


class CommandManagerComponent(commands.Component):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self.cmd_repo = CommandConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]
        LOGGER.info("CommandManager component initialized")

    @commands.group(name="cmd")
    async def cmd(self, ctx: commands.Context["Bot"]) -> None:
        """Command management group. Moderator+ only."""
        if not ctx.chatter.moderator and not ctx.chatter.broadcaster:  # type: ignore[attr-defined]
            return
        if ctx.invoked_subcommand is None:
            await ctx.reply(
                "用法: !cmd a/e/d !指令名 — 新增｜編輯｜刪除 (選項: -cd -role -alias -enable)"
            )

    @cmd.command(name="a")
    async def cmd_add(self, ctx: commands.Context["Bot"], *, args: str | None = None) -> None:
        """Add a custom command."""
        if not ctx.chatter.moderator and not ctx.chatter.broadcaster:  # type: ignore[attr-defined]
            return

        if not args or not args.strip():
            await ctx.reply("用法: !cmd a !指令名 [選項] 回覆文字")
            return

        parts = args.strip().split(maxsplit=1)
        cmd_name = parts[0].lstrip("!").lower()
        remaining = parts[1] if len(parts) > 1 else ""

        if not cmd_name:
            await ctx.reply("用法: !cmd a !指令名 [選項] 回覆文字")
            return

        # Check if command already exists
        channel_id = str(ctx.channel.id)
        existing = await self.cmd_repo.get_config(channel_id, cmd_name)
        if existing:
            await ctx.reply(f"!{cmd_name} 已存在，請用 !cmd e 編輯")
            return

        # Parse options and response text
        options, response_text = _parse_args(remaining)

        if not response_text:
            await ctx.reply("缺少回覆文字: !cmd a !指令名 回覆文字")
            return

        # Build config from options
        cooldown = int(options["cd"]) if "cd" in options else None
        role_input = options.get("role", "everyone")
        min_role = ROLE_ALIASES.get(role_input.lower(), "everyone")
        aliases = options.get("alias")
        enabled = _parse_bool(options["enable"]) if "enable" in options else True

        if enabled is None:
            await ctx.reply("無效的 -enable 值，請使用 on/off")
            return

        config = await self.cmd_repo.upsert_config(
            channel_id,
            cmd_name,
            command_type="custom",
            enabled=enabled,
            custom_response=response_text,
            cooldown=cooldown,
            min_role=min_role,
            aliases=aliases,
        )

        parts_info = [f"!{cmd_name}"]
        if config.aliases:
            parts_info.append(f"別名={config.aliases}")
        if not enabled:
            parts_info.append("已停用")
        await ctx.reply(f"已新增：{' | '.join(parts_info)}")
        LOGGER.info(f"Command added: !{cmd_name} by {ctx.chatter.name}")

    @cmd.command(name="e")
    async def cmd_edit(self, ctx: commands.Context["Bot"], *, args: str | None = None) -> None:
        """Edit a custom command."""
        if not ctx.chatter.moderator and not ctx.chatter.broadcaster:  # type: ignore[attr-defined]
            return

        if not args or not args.strip():
            await ctx.reply("用法: !cmd e !指令名 [選項] [新回覆文字]")
            return

        parts = args.strip().split(maxsplit=1)
        cmd_name = parts[0].lstrip("!").lower()
        remaining = parts[1] if len(parts) > 1 else ""

        if not cmd_name:
            await ctx.reply("用法: !cmd e !指令名 [選項] [新回覆文字]")
            return

        channel_id = str(ctx.channel.id)
        existing = await self.cmd_repo.get_config(channel_id, cmd_name)
        if not existing or existing.command_type != "custom":
            await ctx.reply(f"找不到自訂指令 !{cmd_name}，僅能編輯自訂指令")
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
        if "enable" in options:
            enabled = _parse_bool(options["enable"])
            if enabled is None:
                await ctx.reply("無效的 -enable 值，請使用 on/off")
                return
            kwargs["enabled"] = enabled
        if response_text:
            kwargs["custom_response"] = response_text

        if not kwargs:
            await ctx.reply("請提供要修改的內容，如 -cd=N / -enable=on / 新回覆文字")
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
        if "enable" in options:
            changes.append(f"狀態={'啟用' if config.enabled else '停用'}")

        await ctx.reply(f"已更新 !{cmd_name}：{' | '.join(changes)}")
        LOGGER.info(f"Command edited: !{cmd_name} by {ctx.chatter.name}")

    @cmd.command(name="d")
    async def cmd_delete(self, ctx: commands.Context["Bot"], *, args: str | None = None) -> None:
        """Delete a custom command."""
        if not ctx.chatter.moderator and not ctx.chatter.broadcaster:  # type: ignore[attr-defined]
            return

        if not args or not args.strip():
            await ctx.reply("用法: !cmd d !指令名")
            return

        cmd_name = args.strip().lstrip("!").lower()
        if not cmd_name:
            await ctx.reply("用法: !cmd d !指令名")
            return

        channel_id = str(ctx.channel.id)
        deleted = await self.cmd_repo.delete_config(channel_id, cmd_name)

        if deleted:
            await ctx.reply(f"已刪除 !{cmd_name}")
            LOGGER.info(f"Command deleted: !{cmd_name} by {ctx.chatter.name}")
        else:
            await ctx.reply(f"找不到自訂指令 !{cmd_name}，僅能刪除自訂指令")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(CommandManagerComponent(bot))
    LOGGER.info("CommandManager component loaded")


async def teardown(bot: commands.Bot) -> None:
    LOGGER.info("CommandManager component unloaded")
