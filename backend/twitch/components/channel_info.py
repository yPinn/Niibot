"""Channel info commands: !title / !game / !tags (read for everyone, write for
moderator+) and !marker (moderator+ only, no read side).

Unlike most builtins, permission on title/game/tags is split within a single
command: check_command only has one min_role gate, so the config's min_role
stays "everyone" (anyone can query) and the moderator requirement for the
write path is checked inline with has_role(). All four need the broadcaster's
own channel:manage:broadcast scope for their write/marker call (Twitch has no
moderator-token equivalent for Modify Channel Information or Create Stream
Marker); missing/expired scope surfaces the same reauth chat prompt used by
!subcount et al. Reads (fetch_channel_info, fetch_games) need no scope at all.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import twitchio.ext.commands as commands

from core.component import BotComponent
from core.guards import check_command, has_role
from shared.repositories.command_config import CommandConfigRepository
from utils.command_failure import command_failure_notifier
from utils.reauth import is_scope_error

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER: logging.Logger = logging.getLogger(__name__)

_MAX_TAGS = 10
_MAX_TAG_LEN = 25
_MAX_MARKER_DESC_LEN = 140


class ChannelInfoComponent(BotComponent):
    """Broadcaster-token channel info commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self.cmd_repo = CommandConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.channel_repo = self.bot.channels  # type: ignore[attr-defined]

    def refresh_pool(self, pool) -> None:
        self.cmd_repo.pool = pool

    async def _record_command(self, ctx: commands.Context, command_name: str) -> None:
        try:
            await self.cmd_repo.increment_usage_count(ctx.channel.id, command_name)
        except Exception as e:
            LOGGER.debug("usage count failed for %s: %s", command_name, e)

    async def _notify_reauth(self, ctx: commands.Context) -> None:
        await self.bot._mark_reauth_required(ctx.channel.id)  # type: ignore[attr-defined]

    async def _notify_failure(self, ctx: commands.Context, command: str, message: str) -> None:
        await command_failure_notifier.notify(
            channel_id=ctx.channel.id,
            command=command,
            message=message,
            send_fn=lambda msg: self._ctx_reply(ctx, msg),
        )

    # ------------------------------------------------------------------
    # !title
    # ------------------------------------------------------------------

    @commands.command(name="title", aliases=["台標"])
    async def title(self, ctx: commands.Context, *, new_title: str | None = None) -> None:
        """查詢或修改頻道標題。用法: !title [新標題]（修改需要 Mod 以上）"""
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="title"
        )
        if not config:
            return

        if new_title:
            if not has_role(ctx.chatter, "moderator"):
                await self._ctx_reply(ctx, "只有 Mod 以上可以修改標題")
                return
            try:
                await ctx.broadcaster.modify_channel(title=new_title)
            except Exception as e:
                if is_scope_error(e):
                    await self._notify_reauth(ctx)
                    return
                LOGGER.warning("[%s] !title modify failed: %s", ctx.channel.name, e)
                await self._notify_failure(ctx, "title", "修改標題失敗，請稍後再試")
                return
            await self._ctx_reply(ctx, f"標題已更新為：{new_title}")
            await self._record_command(ctx, "title")
            return

        try:
            info = await ctx.broadcaster.fetch_channel_info()
        except Exception as e:
            LOGGER.warning("[%s] !title fetch failed: %s", ctx.channel.name, e)
            await self._notify_failure(ctx, "title", "查詢失敗，請稍後再試")
            return
        await self._ctx_reply(ctx, f"目前標題：{info.title}")
        await self._record_command(ctx, "title")

    # ------------------------------------------------------------------
    # !game
    # ------------------------------------------------------------------

    @commands.command(name="game", aliases=["分類"])
    async def game(self, ctx: commands.Context, *, new_game: str | None = None) -> None:
        """查詢或修改頻道目前分類。用法: !game [分類名稱]（修改需要 Mod 以上）"""
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="game"
        )
        if not config:
            return

        if new_game:
            if not has_role(ctx.chatter, "moderator"):
                await self._ctx_reply(ctx, "只有 Mod 以上可以修改分類")
                return
            try:
                games = await self.bot.fetch_games(names=[new_game])
            except Exception as e:
                LOGGER.warning("[%s] !game lookup failed: %s", ctx.channel.name, e)
                await self._notify_failure(ctx, "game", "查詢分類失敗，請稍後再試")
                return
            if not games:
                await self._ctx_reply(ctx, f"找不到分類：{new_game}")
                return
            try:
                await ctx.broadcaster.modify_channel(game_id=games[0].id)
            except Exception as e:
                if is_scope_error(e):
                    await self._notify_reauth(ctx)
                    return
                LOGGER.warning("[%s] !game modify failed: %s", ctx.channel.name, e)
                await self._notify_failure(ctx, "game", "修改分類失敗，請稍後再試")
                return
            await self._ctx_reply(ctx, f"分類已更新為：{games[0].name}")
            await self._record_command(ctx, "game")
            return

        try:
            info = await ctx.broadcaster.fetch_channel_info()
        except Exception as e:
            LOGGER.warning("[%s] !game fetch failed: %s", ctx.channel.name, e)
            await self._notify_failure(ctx, "game", "查詢失敗，請稍後再試")
            return
        await self._ctx_reply(ctx, f"目前分類：{info.game_name or '尚未設定'}")
        await self._record_command(ctx, "game")

    # ------------------------------------------------------------------
    # !tags
    # ------------------------------------------------------------------

    @commands.command(name="tags", aliases=["標籤"])
    async def tags(self, ctx: commands.Context, *, new_tags: str | None = None) -> None:
        """查詢或修改頻道標籤。用法: !tags [標籤1,標籤2,...]（修改需要 Mod 以上，
        最多 10 個、每個限 25 字，Twitch 的硬性限制）"""
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="tags"
        )
        if not config:
            return

        if new_tags:
            if not has_role(ctx.chatter, "moderator"):
                await self._ctx_reply(ctx, "只有 Mod 以上可以修改標籤")
                return
            parsed = [t.strip() for t in new_tags.split(",") if t.strip()]
            if len(parsed) > _MAX_TAGS:
                await self._ctx_reply(ctx, f"最多只能設定 {_MAX_TAGS} 個標籤")
                return
            too_long = [t for t in parsed if len(t) > _MAX_TAG_LEN]
            if too_long:
                await self._ctx_reply(
                    ctx, f"標籤過長（上限 {_MAX_TAG_LEN} 字）：{'、'.join(too_long)}"
                )
                return
            try:
                await ctx.broadcaster.modify_channel(tags=parsed)
            except Exception as e:
                if is_scope_error(e):
                    await self._notify_reauth(ctx)
                    return
                LOGGER.warning("[%s] !tags modify failed: %s", ctx.channel.name, e)
                await self._notify_failure(ctx, "tags", "修改標籤失敗，請稍後再試")
                return
            await self._ctx_reply(
                ctx, f"標籤已更新：{'、'.join(parsed) if parsed else '（已清空）'}"
            )
            await self._record_command(ctx, "tags")
            return

        try:
            info = await ctx.broadcaster.fetch_channel_info()
        except Exception as e:
            LOGGER.warning("[%s] !tags fetch failed: %s", ctx.channel.name, e)
            await self._notify_failure(ctx, "tags", "查詢失敗，請稍後再試")
            return
        shown = "、".join(info.tags) if info.tags else "（尚未設定）"
        await self._ctx_reply(ctx, f"目前標籤：{shown}")
        await self._record_command(ctx, "tags")

    # ------------------------------------------------------------------
    # !marker
    # ------------------------------------------------------------------

    @commands.command(name="marker", aliases=["標記"])
    async def marker(self, ctx: commands.Context, *, description: str | None = None) -> None:
        """建立直播標記，方便之後回顧剪輯。用法: !marker [描述]（Mod 以上限定；
        直播中且該頻道已啟用 VOD 才能建立，Twitch 的硬性限制）"""
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="marker"
        )
        if not config:
            return

        if description and len(description) > _MAX_MARKER_DESC_LEN:
            description = description[:_MAX_MARKER_DESC_LEN]

        try:
            result = await ctx.broadcaster.create_stream_marker(
                token_for=ctx.broadcaster.id, description=description
            )
        except Exception as e:
            if is_scope_error(e):
                await self._notify_reauth(ctx)
                return
            LOGGER.warning("[%s] !marker failed: %s", ctx.channel.name, e)
            await self._notify_failure(
                ctx, "marker", "建立標記失敗，請確認目前正在直播且已啟用 VOD"
            )
            return

        minutes, seconds = divmod(result.position, 60)
        await self._ctx_reply(ctx, f"已建立標記（{minutes:02d}:{seconds:02d}）")
        await self._record_command(ctx, "marker")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(ChannelInfoComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
