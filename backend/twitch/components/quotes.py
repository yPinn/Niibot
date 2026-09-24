"""Quote board: !quote (everyone) / !quote add|del (moderator+).

Same split-permission shape as channel_info.py's !title et al: check_command
only has one min_role gate, so the config stays "everyone" and the add/del
subcommands check has_role() inline.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import twitchio.ext.commands as commands

from core.component import BotComponent
from core.guards import check_command, has_role
from shared.repositories.command_config import CommandConfigRepository
from shared.repositories.quote import QuoteRepository

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER: logging.Logger = logging.getLogger(__name__)

_MAX_QUOTE_LEN = 450


class QuoteComponent(BotComponent):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self.cmd_repo = CommandConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.channel_repo = self.bot.channels  # type: ignore[attr-defined]
        self.quote_repo = QuoteRepository(self.bot.token_database)  # type: ignore[attr-defined]

    def refresh_pool(self, pool) -> None:
        self.cmd_repo.pool = pool
        self.quote_repo.pool = pool

    async def _record_command(self, ctx: commands.Context, command_name: str) -> None:
        try:
            await self.cmd_repo.increment_usage_count(ctx.channel.id, command_name)
        except Exception as e:
            LOGGER.debug("usage count failed for %s: %s", command_name, e)

    @commands.command(name="quote", aliases=["語錄"])
    async def quote(self, ctx: commands.Context, *, args: str | None = None) -> None:
        """查詢、新增或刪除語錄。用法:
        !quote — 隨機一則
        !quote <編號> — 指定編號
        !quote add <內容> — 新增（Mod 以上）
        !quote del <編號> — 刪除（Mod 以上）
        """
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="quote"
        )
        if not config:
            return

        channel_id = ctx.channel.id
        text = (args or "").strip()
        parts = text.split(maxsplit=1)
        sub = parts[0].lower() if parts else ""
        rest = parts[1].strip() if len(parts) > 1 else ""

        if sub == "add":
            await self._add(ctx, channel_id, rest)
            return
        if sub == "del":
            await self._delete(ctx, channel_id, rest)
            return

        await self._show(ctx, channel_id, text)

    async def _add(self, ctx: commands.Context, channel_id: str, body: str) -> None:
        if not has_role(ctx.chatter, "moderator"):
            await self._ctx_reply(ctx, "只有 Mod 以上可以新增語錄")
            return
        if not body:
            await self._ctx_reply(ctx, "用法：!quote add <內容>")
            return
        if len(body) > _MAX_QUOTE_LEN:
            await self._ctx_reply(ctx, f"語錄過長（上限 {_MAX_QUOTE_LEN} 字）")
            return

        creator = ctx.chatter.display_name or ctx.chatter.name or "?"
        try:
            created = await self.quote_repo.add(channel_id, body, creator)
        except Exception as e:
            LOGGER.warning("[%s] !quote add failed: %s", ctx.channel.name, e)
            await self._ctx_reply(ctx, "新增語錄失敗，請稍後再試")
            return
        await self._ctx_reply(ctx, f"已新增語錄 #{created.quote_number}")
        await self._record_command(ctx, "quote")

    async def _delete(self, ctx: commands.Context, channel_id: str, raw_number: str) -> None:
        if not has_role(ctx.chatter, "moderator"):
            await self._ctx_reply(ctx, "只有 Mod 以上可以刪除語錄")
            return
        if not raw_number.isdigit():
            await self._ctx_reply(ctx, "用法：!quote del <編號>")
            return

        try:
            deleted = await self.quote_repo.delete(channel_id, int(raw_number))
        except Exception as e:
            LOGGER.warning("[%s] !quote del failed: %s", ctx.channel.name, e)
            await self._ctx_reply(ctx, "刪除語錄失敗，請稍後再試")
            return
        await self._ctx_reply(
            ctx, f"已刪除語錄 #{raw_number}" if deleted else f"找不到語錄 #{raw_number}"
        )
        await self._record_command(ctx, "quote")

    async def _show(self, ctx: commands.Context, channel_id: str, text: str) -> None:
        try:
            found = (
                await self.quote_repo.get_by_number(channel_id, int(text))
                if text.isdigit()
                else await self.quote_repo.get_random(channel_id)
            )
        except Exception as e:
            LOGGER.warning("[%s] !quote lookup failed: %s", ctx.channel.name, e)
            await self._ctx_reply(ctx, "查詢失敗，請稍後再試")
            return

        if not found:
            await self._ctx_reply(ctx, "還沒有語錄，用 !quote add <內容> 新增第一則吧")
            return
        await self._ctx_reply(ctx, f"#{found.quote_number}：{found.quote_text}")
        await self._record_command(ctx, "quote")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(QuoteComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
