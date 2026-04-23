"""Chat-based command/trigger management: !cmd a/e/d.

Syntax:
    !cmd a !指令名 [options] 回覆文字    — 新增自訂指令
    !cmd a 觸發詞  [options] 回覆文字   — 新增自動回應（無 ! 前綴）
    !cmd e !指令名 [options] [新回覆文字]
    !cmd e 觸發詞  [options] [新回覆文字]
    !cmd d !指令名
    !cmd d 觸發詞

Options (指令):
    -cd=N          Cooldown in seconds
    -role=X        Min role: everyone/sub/vip/mod/broadcaster
    -alias=a,b,c   Comma-separated aliases
    -enable=on/off Toggle enabled state

Options (觸發，額外):
    -match=X       Match type: contains/startswith/exact/regex (default: contains)
    -cs=on/off     Case sensitive (default: off)

Examples:
    !cmd a !你好 $(user) 你好呀！
    !cmd a 你好 $(user) 你好呀！
    !cmd a !問候 -cd=30 -alias=greeting,hey $(user) 嗨！
    !cmd e !問候 -cd=60
    !cmd d !問候
    !cmd d 你好
"""

import asyncio
import logging
import re
from typing import TYPE_CHECKING

from twitchio.ext import commands

from shared.repositories.command_config import CommandConfigRepository
from utils.trigger_matching import validate_regex_pattern

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER: logging.Logger = logging.getLogger(__name__)

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

_MATCH_TYPES = {"contains", "startswith", "exact", "regex"}


def _sanitize_trigger_name(pattern: str) -> str:
    """Derive a stable DB key from a trigger pattern."""
    name = re.sub(r"[^a-z0-9_-]", "_", pattern.lower())
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:50] or "trigger"


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

    def refresh_pool(self, pool) -> None:
        self.cmd_repo.pool = pool

    @commands.Component.guard()
    def _is_mod(self, ctx: commands.Context) -> bool:
        # .moderator already includes broadcaster (see Chatter.moderator source)
        return ctx.chatter.moderator  # type: ignore[attr-defined]

    @commands.group(name="cmd")
    async def cmd(self, ctx: commands.Context["Bot"]) -> None:
        """Command management group. Moderator+ only."""
        if ctx.invoked_subcommand is None:
            await ctx.reply(
                "用法: !cmd a/e/d !指令名 — 新增｜編輯｜刪除 (選項: -cd -role -alias -enable)"
            )

    @cmd.command(name="a", aliases=["add"])
    async def cmd_add(self, ctx: commands.Context["Bot"], *, args: str | None = None) -> None:
        """Add a custom command (!prefix) or auto-response trigger (no prefix)."""
        if not ctx.chatter.moderator:  # type: ignore[attr-defined]
            return
        if not args or not args.strip():
            await ctx.reply("用法: !cmd a !指令名 回覆 / !cmd a 觸發詞 回覆")
            return

        parts = args.strip().split(maxsplit=1)
        first = parts[0]
        remaining = parts[1] if len(parts) > 1 else ""
        is_command = first.startswith("!")
        channel_id = str(ctx.channel.id)

        options, response_text = _parse_args(remaining)

        if not response_text:
            await ctx.reply("缺少回覆文字")
            return

        if "cd" in options:
            try:
                cooldown = int(options["cd"])
            except ValueError:
                await ctx.reply("冷卻時間必須是整數（秒）")
                return
        else:
            cooldown = None
        role_input = options.get("role", "everyone")
        min_role = ROLE_ALIASES.get(role_input.lower(), "everyone")
        enabled = _parse_bool(options["enable"]) if "enable" in options else True
        if enabled is None:
            await ctx.reply("無效的 -enable 值，請使用 on/off")
            return

        if is_command:
            cmd_name = first.lstrip("!").lower()
            if not cmd_name:
                await ctx.reply("用法: !cmd a !指令名 回覆文字")
                return
            existing = await self.cmd_repo.get_config(channel_id, cmd_name)
            if existing:
                await ctx.reply(f"!{cmd_name} 已存在，請用 !cmd e 編輯")
                return
            aliases = options.get("alias")
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
            preview = response_text[:30] + ("…" if len(response_text) > 30 else "")
            reply = f"已新增 !{cmd_name} → {preview}"
            if config.aliases:
                reply += f" | 別名: {config.aliases}"
            if not enabled:
                reply += " | 已停用"
            await ctx.reply(reply)
            LOGGER.info(f"Command added: !{cmd_name} by {ctx.chatter.name}")
        else:
            pattern = first
            match_type = options.get("match", "contains")
            if match_type not in _MATCH_TYPES:
                await ctx.reply(f"無效的 -match 值，請使用: {', '.join(_MATCH_TYPES)}")
                return
            case_sensitive_raw = _parse_bool(options.get("cs", "off"))
            if case_sensitive_raw is None:
                await ctx.reply("無效的 -cs 值，請使用 on/off")
                return
            case_sensitive = case_sensitive_raw
            if match_type == "regex":
                is_safe = await asyncio.get_running_loop().run_in_executor(
                    None, validate_regex_pattern, pattern
                )
                if not is_safe:
                    await ctx.reply("無效或不安全的 Regex 模式（可能導致 ReDoS），已拒絕")
                    return
            trigger_name = _sanitize_trigger_name(pattern)
            existing_trigger = await self.bot.message_trigger_configs.get_by_name(
                channel_id, trigger_name
            )
            if existing_trigger and existing_trigger.pattern != pattern:
                await ctx.reply(
                    f"觸發詞與現有「{existing_trigger.pattern}」衝突，"
                    f"請用 !cmd e {existing_trigger.pattern} 編輯，或先 !cmd d {existing_trigger.pattern} 刪除"
                )
                return
            if existing_trigger:
                await ctx.reply(f"「{pattern}」已存在，請用 !cmd e 編輯")
                return
            await self.bot.message_trigger_configs.upsert(
                channel_id,
                trigger_name,
                match_type=match_type,
                pattern=pattern,
                case_sensitive=case_sensitive,
                response=response_text,
                min_role=min_role,
                cooldown=cooldown,
                priority=0,
                enabled=enabled,
            )
            preview = response_text[:30] + ("…" if len(response_text) > 30 else "")
            await ctx.reply(f"已新增觸發 {pattern} → {preview}")
            LOGGER.info(f"Trigger added: '{pattern}' by {ctx.chatter.name}")

    @cmd.command(name="e", aliases=["edit"])
    async def cmd_edit(self, ctx: commands.Context["Bot"], *, args: str | None = None) -> None:
        """Edit a custom command or trigger."""
        if not ctx.chatter.moderator:  # type: ignore[attr-defined]
            return
        if not args or not args.strip():
            await ctx.reply("用法: !cmd e !指令名 [選項] / !cmd e 觸發詞 [選項] [新回覆文字]")
            return

        parts = args.strip().split(maxsplit=1)
        first = parts[0]
        remaining = parts[1] if len(parts) > 1 else ""
        is_command = first.startswith("!")
        channel_id = str(ctx.channel.id)
        options, response_text = _parse_args(remaining)

        if is_command:
            cmd_name = first.lstrip("!").lower()
            if not cmd_name:
                await ctx.reply("用法: !cmd e !指令名 [選項] [新回覆文字]")
                return

            existing = await self.cmd_repo.get_config(channel_id, cmd_name)
            if not existing or existing.command_type != "custom":
                await ctx.reply(f"找不到自訂指令 !{cmd_name}，僅能編輯自訂指令")
                return

            kwargs: dict = {}
            if "cd" in options:
                try:
                    kwargs["cooldown"] = int(options["cd"])
                except ValueError:
                    await ctx.reply("冷卻時間必須是整數（秒）")
                    return
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
                channel_id, cmd_name, command_type="custom", **kwargs
            )

            changes = []
            if response_text:
                preview = response_text[:25] + ("…" if len(response_text) > 25 else "")
                changes.append(f"回覆: {preview}")
            if "cd" in options:
                changes.append(f"冷卻: {config.cooldown}s")
            if "role" in options:
                changes.append(f"權限: {config.min_role}")
            if "alias" in options:
                changes.append(f"別名: {config.aliases}")
            if "enable" in options:
                changes.append("啟用" if config.enabled else "停用")

            await ctx.reply(f"已更新 !{cmd_name} — {' | '.join(changes)}")
            LOGGER.info(f"Command edited: !{cmd_name} by {ctx.chatter.name}")

        else:
            # Edit trigger by pattern
            pattern = first
            trigger_name = _sanitize_trigger_name(pattern)
            existing_trigger = await self.bot.message_trigger_configs.get_by_name(
                channel_id, trigger_name
            )
            if not existing_trigger:
                await ctx.reply(f"找不到觸發詞：{pattern}")
                return

            tkwargs: dict = {}
            if "cd" in options:
                try:
                    tkwargs["cooldown"] = int(options["cd"])
                except ValueError:
                    await ctx.reply("冷卻時間必須是整數（秒）")
                    return
            if "role" in options:
                tkwargs["min_role"] = ROLE_ALIASES.get(options["role"].lower(), "everyone")
            if "match" in options:
                if options["match"] not in _MATCH_TYPES:
                    await ctx.reply(f"無效的 -match 值，請使用: {', '.join(_MATCH_TYPES)}")
                    return
                tkwargs["match_type"] = options["match"]
                if options["match"] == "regex":
                    is_safe = await asyncio.get_running_loop().run_in_executor(
                        None, validate_regex_pattern, pattern
                    )
                    if not is_safe:
                        await ctx.reply("無效或不安全的 Regex 模式（可能導致 ReDoS），已拒絕")
                        return
            if "cs" in options:
                cs = _parse_bool(options["cs"])
                if cs is None:
                    await ctx.reply("無效的 -cs 值，請使用 on/off")
                    return
                tkwargs["case_sensitive"] = cs
            if "enable" in options:
                enabled_t = _parse_bool(options["enable"])
                if enabled_t is None:
                    await ctx.reply("無效的 -enable 值，請使用 on/off")
                    return
                tkwargs["enabled"] = enabled_t
            if response_text:
                tkwargs["response"] = response_text

            if not tkwargs:
                await ctx.reply("請提供要修改的內容，如 -cd=N / -enable=on / 新回覆文字")
                return

            # Only pass fields being changed; None → COALESCE keeps existing DB value
            await self.bot.message_trigger_configs.upsert(
                channel_id,
                trigger_name,
                match_type=tkwargs.get("match_type"),
                case_sensitive=tkwargs.get("case_sensitive"),
                response=tkwargs.get("response"),
                min_role=tkwargs.get("min_role"),
                cooldown=tkwargs.get("cooldown"),
                enabled=tkwargs.get("enabled"),
            )

            changes = []
            if response_text:
                preview = response_text[:25] + ("…" if len(response_text) > 25 else "")
                changes.append(f"回覆: {preview}")
            if "cd" in options:
                changes.append(f"冷卻: {options['cd']}s")
            if "role" in options:
                changes.append(f"權限: {options['role']}")
            if "match" in options:
                changes.append(f"比對: {options['match']}")
            if "enable" in options:
                val = _parse_bool(options["enable"])
                changes.append("啟用" if val else "停用")

            await ctx.reply(f"已更新觸發 {pattern} — {' | '.join(changes)}")
            LOGGER.info(f"Trigger edited: '{pattern}' by {ctx.chatter.name}")

    @cmd.command(name="d", aliases=["delete"])
    async def cmd_delete(self, ctx: commands.Context["Bot"], *, args: str | None = None) -> None:
        """Delete a custom command or trigger."""
        if not ctx.chatter.moderator:  # type: ignore[attr-defined]
            return
        if not args or not args.strip():
            await ctx.reply("用法: !cmd d !指令名 / !cmd d 觸發詞")
            return

        target = args.strip()
        channel_id = str(ctx.channel.id)

        if not target.startswith("!"):
            # Delete trigger by pattern
            trigger_name = _sanitize_trigger_name(target)
            deleted = await self.bot.message_trigger_configs.delete(channel_id, trigger_name)
            if deleted:
                await ctx.reply(f"已刪除觸發：{target}")
                LOGGER.info(f"Trigger deleted: '{target}' by {ctx.chatter.name}")
            else:
                await ctx.reply(f"找不到觸發詞：{target}")
            return

        cmd_name = target.lstrip("!").lower()
        if not cmd_name:
            await ctx.reply("用法: !cmd d !指令名")
            return
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
