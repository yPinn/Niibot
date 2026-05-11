"""Crosshair bot commands: !xhc and subcommands.

Syntax:
    !xhc                      — 顯示準星收藏頁面連結（所有人）
    !xhc <名稱>               — 查詢並分享準星代碼（所有人，15s cooldown）
    !xhc a <名稱> <代碼>       — 新增準星（Mod+）
    !xhc e <名稱> <新代碼>     — 編輯準星代碼（Mod+）
    !xhc d <名稱>             — 刪除準星（Mod+）

<名稱> may contain spaces; <代碼> is always the last whitespace-delimited token
since Valorant crosshair codes contain no spaces.
"""

import logging
import re
import time
from typing import TYPE_CHECKING

from twitchio.ext import commands

from core.component import BotComponent
from core.config import get_settings
from core.guards import check_command
from shared.repositories.command_config import CommandConfigRepository
from shared.repositories.crosshair import CrosshairRepository

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER: logging.Logger = logging.getLogger(__name__)

FRONTEND_URL = get_settings().frontend_url.rstrip("/")

_VIEWER_SHARE_COOLDOWN = 15  # seconds

_OPT_PATTERN = re.compile(r"-(\w+)=(\S+)")


def _parse_opts(raw: str) -> tuple[dict[str, str], str]:
    """Extract -key=value tokens from raw args.

    Returns (opts_dict, remaining_text). Consistent with command_manager parsing.
    """
    opts: dict[str, str] = {}
    rest: list[str] = []
    for token in raw.split():
        m = _OPT_PATTERN.fullmatch(token)
        if m:
            opts[m.group(1).lower()] = m.group(2)
        else:
            rest.append(token)
    return opts, " ".join(rest)


def _split_name_code(args: str) -> tuple[str, str] | None:
    """Split '<name> <code>' where code is always the last token.

    Returns (name, code) or None if there are fewer than two tokens.
    """
    parts = args.strip().rsplit(maxsplit=1)
    if len(parts) < 2:
        return None
    return parts[0].strip(), parts[1].strip()


class CrosshairCommandsComponent(BotComponent):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self.cmd_repo = CommandConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.channel_repo = self.bot.channels  # type: ignore[attr-defined]
        self.xhair_repo = CrosshairRepository(self.bot.token_database)  # type: ignore[attr-defined]
        # viewer share cooldown: key = "{channel_id}:{user_id}"
        self._share_cd: dict[str, float] = {}

    def refresh_pool(self, pool) -> None:
        self.cmd_repo.pool = pool
        self.xhair_repo.pool = pool

    @property
    def _has_analytics(self) -> bool:
        return hasattr(self.bot, "_active_sessions") and hasattr(self.bot, "analytics")

    async def _record_command(self, ctx: commands.Context, command_name: str) -> None:
        try:
            channel_id = ctx.channel.id
            await self.cmd_repo.increment_usage_count(channel_id, command_name)
            if self._has_analytics:
                session_id = self.bot._active_sessions.get(channel_id)  # type: ignore[attr-defined]
                if session_id:
                    await self.bot.analytics.record_command_usage(  # type: ignore[attr-defined]
                        session_id=session_id,
                        channel_id=channel_id,
                        command_name=f"!{command_name}",
                    )
        except Exception as e:
            LOGGER.error("Failed to record command usage: %s", e)

    # ── !xhc ──────────────────────────────────────────────────────────────────

    @commands.group(name="xhc")
    async def xhc(self, ctx: commands.Context) -> None:
        """Show crosshairs page link, or look up a crosshair by name."""
        if ctx.invoked_subcommand is not None:
            return

        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="crosshairs"
        )
        if not config:
            return

        # Parse anything after "!xhc" from the raw message
        parts = (ctx.message.text if ctx.message else "").strip().split(maxsplit=1)
        name = parts[1].strip() if len(parts) > 1 else None

        if not name:
            channel_name = ctx.channel.name
            await self._ctx_reply(ctx, f"準星收藏： {FRONTEND_URL}/{channel_name}/crosshairs")
            await self._record_command(ctx, "crosshairs")
            return

        # Name provided → look up and echo (with per-user cooldown)
        key = f"{ctx.channel.id}:{ctx.chatter.id}"
        now = time.monotonic()
        if now - self._share_cd.get(key, 0.0) < _VIEWER_SHARE_COOLDOWN:
            return
        self._share_cd[key] = now
        # Prune entries older than 2× cooldown to bound memory
        if len(self._share_cd) > 500:
            cutoff = now - _VIEWER_SHARE_COOLDOWN * 2
            self._share_cd = {k: v for k, v in self._share_cd.items() if v > cutoff}

        channel_id = str(ctx.channel.id)
        crosshair = await self.xhair_repo.get_by_name(channel_id, name)
        if not crosshair:
            await self._ctx_reply(ctx, f"找不到準星「{name}」")
            return

        code = crosshair["code"]
        preview = code[:40] + ("…" if len(code) > 40 else "")
        await self._ctx_reply(ctx, f"【{crosshair['name']}】{preview}")
        await self._record_command(ctx, "crosshairs")

    # ── !xhc a <名稱> <代碼> ─────────────────────────────────────────────────

    @xhc.command(name="a")
    async def xhc_add(self, ctx: commands.Context, *, args: str | None = None) -> None:
        """Add a crosshair to the channel repo. Mod/Broadcaster only.

        Usage: !xhc a <準星名稱> <準星代碼>
        """
        if not ctx.chatter.moderator and not ctx.chatter.broadcaster:  # type: ignore[attr-defined]
            return
        if not args:
            await self._ctx_reply(ctx, "用法：!xhc a <準星名稱> <準星代碼>")
            return

        opts, remaining = _parse_opts(args)
        parsed = _split_name_code(remaining)
        if not parsed:
            await self._ctx_reply(ctx, "用法：!xhc a <準星名稱> <準星代碼> [-desc=備註]")
            return
        name, code = parsed
        desc = opts.get("desc")

        channel_id = str(ctx.channel.id)
        existing = await self.xhair_repo.get_by_name(channel_id, name)
        if existing:
            await self._ctx_reply(ctx, f"「{name}」已存在，請用 !xhc e 編輯")
            return
        try:
            await self.xhair_repo.create(
                channel_id, game="valorant", name=name, code=code, description=desc
            )
            preview = code[:25] + ("…" if len(code) > 25 else "")
            reply = f"已新增準星「{name}」→ {preview}"
            if desc:
                reply += f" | {desc}"
            await self._ctx_reply(ctx, reply)
            LOGGER.info("Crosshair added by %s: %s", ctx.chatter.name, name)
        except Exception:
            LOGGER.exception("Failed to add crosshair via !xhc a")
            await self._ctx_reply(ctx, "新增失敗，請稍後再試")

    # ── !xhc e <名稱> <新代碼> ───────────────────────────────────────────────

    @xhc.command(name="e")
    async def xhc_edit(self, ctx: commands.Context, *, args: str | None = None) -> None:
        """Edit a crosshair's code by name. Mod/Broadcaster only.

        Usage: !xhc e <準星名稱> <新準星代碼>
        """
        if not ctx.chatter.moderator and not ctx.chatter.broadcaster:  # type: ignore[attr-defined]
            return
        if not args:
            await self._ctx_reply(ctx, "用法：!xhc e <準星名稱> <新準星代碼>")
            return

        opts, remaining = _parse_opts(args)
        parsed = _split_name_code(remaining)
        if not parsed:
            await self._ctx_reply(ctx, "用法：!xhc e <準星名稱> <新準星代碼> [-desc=備註]")
            return
        name, code = parsed

        channel_id = str(ctx.channel.id)
        existing = await self.xhair_repo.get_by_name(channel_id, name)
        if not existing:
            await self._ctx_reply(ctx, f"找不到準星「{name}」")
            return

        fields: dict = {"code": code}
        if "desc" in opts:
            fields["description"] = opts["desc"]

        try:
            await self.xhair_repo.update(existing["id"], channel_id, fields=fields)
            preview = code[:25] + ("…" if len(code) > 25 else "")
            reply = f"已更新準星「{name}」→ {preview}"
            if "desc" in opts:
                reply += f" | {opts['desc']}"
            await self._ctx_reply(ctx, reply)
            LOGGER.info("Crosshair edited by %s: %s", ctx.chatter.name, name)
        except Exception:
            LOGGER.exception("Failed to edit crosshair via !xhc e")
            await self._ctx_reply(ctx, "編輯失敗，請稍後再試")

    # ── !xhc d <名稱> ────────────────────────────────────────────────────────

    @xhc.command(name="d")
    async def xhc_delete(self, ctx: commands.Context, *, args: str | None = None) -> None:
        """Delete a crosshair by name. Mod/Broadcaster only.

        Usage: !xhc d <準星名稱>
        """
        if not ctx.chatter.moderator and not ctx.chatter.broadcaster:  # type: ignore[attr-defined]
            return
        if not args or not args.strip():
            await self._ctx_reply(ctx, "用法：!xhc d <準星名稱>")
            return

        name = args.strip()
        channel_id = str(ctx.channel.id)
        existing = await self.xhair_repo.get_by_name(channel_id, name)
        if not existing:
            await self._ctx_reply(ctx, f"找不到準星「{name}」")
            return

        try:
            await self.xhair_repo.delete(existing["id"], channel_id)
            await self._ctx_reply(ctx, f"已刪除準星「{name}」")
            LOGGER.info("Crosshair deleted by %s: %s", ctx.chatter.name, name)
        except Exception:
            LOGGER.exception("Failed to delete crosshair via !xhc d")
            await self._ctx_reply(ctx, "刪除失敗，請稍後再試")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(CrosshairCommandsComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
