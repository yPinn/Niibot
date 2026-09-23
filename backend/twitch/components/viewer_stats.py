"""Viewer self-service lookups: !followage / !subage / !subcount / !bits / !accountage.

All Twitch reads follow the master-slave rule:
  - followers, account age → bot token (public/moderator-readable data)
  - subs/bits  → broadcaster token (no moderator-token equivalent on Twitch)

Missing-scope broadcaster tokens surface a reauth chat prompt exactly once per
episode (see utils/reauth.py). A 401 that isn't scope-related, and all other
Twitch/lookup failures, degrade to a generic "查詢失敗" line throttled per
(channel, command) via utils/command_failure.py.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx
from twitchio.ext import commands

from core.component import BotComponent
from core.config import get_settings
from core.guards import check_command
from shared.repositories.command_config import CommandConfigRepository
from utils.command_failure import command_failure_notifier
from utils.reauth import is_scope_error

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER: logging.Logger = logging.getLogger(__name__)

_TIER_NAMES = {"1000": "T1", "2000": "T2", "3000": "T3"}


def _humanise_since(start: datetime) -> str:
    """Render the elapsed time since *start* as e.g. '1 年 2 個月 3 天'."""
    now = datetime.now(UTC)
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    days = max((now - start).days, 0)
    years, rem = divmod(days, 365)
    months, day = divmod(rem, 30)
    parts = []
    if years:
        parts.append(f"{years} 年")
    if months:
        parts.append(f"{months} 個月")
    if day or not parts:
        parts.append(f"{day} 天")
    return " ".join(parts)


def _subscriber_months(ctx: commands.Context) -> int | None:
    """Read Twitch's cumulative subscription months from the invoking chat badge."""
    for badge in getattr(ctx.chatter, "badges", []):
        if badge.set_id != "subscriber":
            continue
        try:
            months = int(badge.info)
        except (TypeError, ValueError):
            return None
        return months if months > 0 else None
    return None


class ViewerStatsComponent(BotComponent):
    """Follow / subscription / bits lookup commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self.cmd_repo = CommandConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.channel_repo = self.bot.channels  # type: ignore[attr-defined]
        self._client_id: str = get_settings().twitch_client_id

    def refresh_pool(self, pool) -> None:
        self.cmd_repo.pool = pool

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _helix_get(
        self,
        path: str,
        params: dict,
        token: str,
        *,
        token_for: str,
    ) -> httpx.Response:
        return await self.bot._coordinated_helix_get(
            path,
            token=token,
            token_for=token_for,
            params=params,
        )

    async def _broadcaster_token(self, channel_id: str) -> str | None:
        tok = await self.channel_repo.get_token(channel_id)
        return tok.token if tok else None

    async def _bot_token(self, channel_id: str) -> str | None:
        tok = await self.channel_repo.get_token(self.bot.sender_for(channel_id), "bot")
        return tok.token if tok else None

    async def _notify_reauth(self, ctx: commands.Context) -> None:
        await self.bot._mark_reauth_required(ctx.channel.id)  # type: ignore[attr-defined]

    async def _notify_failure(self, ctx: commands.Context, command: str, message: str) -> None:
        await command_failure_notifier.notify(
            channel_id=ctx.channel.id,
            command=command,
            message=message,
            send_fn=lambda msg: self._ctx_reply(ctx, msg),
        )

    async def _guard(self, ctx: commands.Context, name: str) -> bool:
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name=name
        )
        return config is not None

    async def _record(self, ctx: commands.Context, name: str) -> None:
        try:
            await self.cmd_repo.increment_usage_count(ctx.channel.id, name)
        except Exception as e:
            LOGGER.debug("usage count failed for %s: %s", name, e)

    # ------------------------------------------------------------------
    # !followage
    # ------------------------------------------------------------------

    @commands.command(name="followage", aliases=["追隨時間"])
    async def followage(self, ctx: commands.Context) -> None:
        """查詢自己追隨這個頻道多久。用法: !followage / !追隨時間"""
        if not await self._guard(ctx, "followage"):
            return

        channel_id = ctx.channel.id
        user_id = ctx.chatter.id
        name = ctx.chatter.display_name or ctx.chatter.name

        if user_id == channel_id:
            await self._ctx_reply(ctx, f"@{name} 這是你自己的頻道 KappaPride")
            await self._record(ctx, "followage")
            return

        token = await self._bot_token(channel_id)
        if not token:
            await self._notify_failure(ctx, "followage", "查詢失敗，請稍後再試")
            return

        try:
            resp = await self._helix_get(
                "channels/followers",
                {
                    "broadcaster_id": channel_id,
                    "user_id": user_id,
                    "moderator_id": self.bot.sender_for(channel_id),
                },
                token,
                token_for=self.bot.sender_for(channel_id),
            )
        except Exception as e:
            LOGGER.warning("[%s] followage error: %s", ctx.channel.name, e)
            await self._notify_failure(ctx, "followage", "查詢失敗，請稍後再試")
            return

        if resp.status_code != 200:
            LOGGER.warning("[%s] followage %s", ctx.channel.name, resp.status_code)
            await self._notify_failure(ctx, "followage", "查詢失敗，請稍後再試")
            return

        data = resp.json().get("data", [])
        if not data:
            await self._ctx_reply(ctx, f"@{name} 還沒追隨這個頻道喔")
        else:
            followed_at = datetime.fromisoformat(data[0]["followed_at"].replace("Z", "+00:00"))
            await self._ctx_reply(ctx, f"@{name} 已追隨 {_humanise_since(followed_at)}")
        await self._record(ctx, "followage")

    # ------------------------------------------------------------------
    # !subage
    # ------------------------------------------------------------------

    @commands.command(name="subage", aliases=["訂閱資訊"])
    async def subage(self, ctx: commands.Context) -> None:
        """查詢自己的累積訂閱月數與目前方案。用法: !subage / !訂閱資訊"""
        if not await self._guard(ctx, "subage"):
            return

        channel_id = ctx.channel.id
        user_id = ctx.chatter.id
        name = ctx.chatter.display_name or ctx.chatter.name

        if user_id == channel_id:
            await self._ctx_reply(ctx, f"@{name} 你是這裡的實況主 👑")
            await self._record(ctx, "subage")
            return

        token = await self._broadcaster_token(channel_id)
        if not token:
            await self._notify_failure(ctx, "subage", "查詢失敗，請稍後再試")
            return

        try:
            resp = await self._helix_get(
                "subscriptions",
                {"broadcaster_id": channel_id, "user_id": user_id},
                token,
                token_for=channel_id,
            )
        except Exception as e:
            LOGGER.warning("[%s] subage error: %s", ctx.channel.name, e)
            await self._notify_failure(ctx, "subage", "查詢失敗，請稍後再試")
            return

        if is_scope_error(resp):
            await self._notify_reauth(ctx)
            return
        if resp.status_code != 200:
            await self._notify_failure(ctx, "subage", "查詢失敗，請稍後再試")
            return

        data = resp.json().get("data", [])
        if not data:
            await self._ctx_reply(ctx, f"@{name} 目前沒有訂閱這個頻道")
        else:
            sub = data[0]
            tier = _TIER_NAMES.get(sub.get("tier", ""), sub.get("tier", "?"))
            gifted = "（禮物訂閱）" if sub.get("is_gift") else ""
            months = _subscriber_months(ctx)
            month_text = f"累積訂閱 {months} 個月，" if months is not None else ""
            await self._ctx_reply(ctx, f"@{name} {month_text}目前是 {tier} 訂閱者{gifted}")
        await self._record(ctx, "subage")

    # ------------------------------------------------------------------
    # !subcount
    # ------------------------------------------------------------------

    @commands.command(name="subcount", aliases=["訂閱數"])
    async def subcount(self, ctx: commands.Context) -> None:
        """顯示頻道目前訂閱總數。用法: !subcount / !訂閱數"""
        if not await self._guard(ctx, "subcount"):
            return

        channel_id = ctx.channel.id
        token = await self._broadcaster_token(channel_id)
        if not token:
            await self._notify_failure(ctx, "subcount", "查詢失敗，請稍後再試")
            return

        try:
            resp = await self._helix_get(
                "subscriptions",
                {"broadcaster_id": channel_id, "first": 1},
                token,
                token_for=channel_id,
            )
        except Exception as e:
            LOGGER.warning("[%s] subcount error: %s", ctx.channel.name, e)
            await self._notify_failure(ctx, "subcount", "查詢失敗，請稍後再試")
            return

        if is_scope_error(resp):
            await self._notify_reauth(ctx)
            return
        if resp.status_code != 200:
            await self._notify_failure(ctx, "subcount", "查詢失敗，請稍後再試")
            return

        total = resp.json().get("total", 0)
        await self._ctx_reply(ctx, f"目前共有 {total} 位訂閱者，感謝大家的支持 💜")
        await self._record(ctx, "subcount")

    # ------------------------------------------------------------------
    # !bits
    # ------------------------------------------------------------------

    @commands.command(name="bits", aliases=["小奇點"])
    async def bits(self, ctx: commands.Context) -> None:
        """查詢自己在這個頻道的小奇點排名與總額。用法: !bits / !小奇點"""
        if not await self._guard(ctx, "bits"):
            return

        channel_id = ctx.channel.id
        user_id = ctx.chatter.id
        name = ctx.chatter.display_name or ctx.chatter.name

        token = await self._broadcaster_token(channel_id)
        if not token:
            await self._notify_failure(ctx, "bits", "查詢失敗，請稍後再試")
            return

        try:
            resp = await self._helix_get(
                "bits/leaderboard",
                {"user_id": user_id, "period": "all"},
                token,
                token_for=channel_id,
            )
        except Exception as e:
            LOGGER.warning("[%s] bits error: %s", ctx.channel.name, e)
            await self._notify_failure(ctx, "bits", "查詢失敗，請稍後再試")
            return

        if is_scope_error(resp):
            await self._notify_reauth(ctx)
            return
        if resp.status_code != 200:
            await self._notify_failure(ctx, "bits", "查詢失敗，請稍後再試")
            return

        data = resp.json().get("data", [])
        if not data:
            await self._ctx_reply(ctx, f"@{name} 還沒有在這個頻道投過小奇點")
        else:
            entry = data[0]
            await self._ctx_reply(
                ctx,
                f"@{name} 小奇點排名第 {entry.get('rank', '?')} 名，"
                f"累計 {entry.get('score', 0)} 顆 ✨",
            )
        await self._record(ctx, "bits")

    # ------------------------------------------------------------------
    # !accountage
    # ------------------------------------------------------------------

    @commands.command(name="accountage", aliases=["帳號年齡"])
    async def accountage(self, ctx: commands.Context, *, target: str | None = None) -> None:
        """查詢自己或指定使用者的 Twitch 帳號建立時間。用法: !accountage [使用者]"""
        if not await self._guard(ctx, "accountage"):
            return

        channel_id = ctx.channel.id
        login = (target or "").strip().lstrip("@").lower()
        params = {"login": login} if login else {"id": ctx.chatter.id}

        token = await self._bot_token(channel_id)
        if not token:
            await self._notify_failure(ctx, "accountage", "查詢失敗，請稍後再試")
            return

        try:
            resp = await self._helix_get(
                "users",
                params,
                token,
                token_for=self.bot.sender_for(channel_id),
            )
        except Exception as e:
            LOGGER.warning("[%s] accountage error: %s", ctx.channel.name, e)
            await self._notify_failure(ctx, "accountage", "查詢失敗，請稍後再試")
            return

        if resp.status_code != 200:
            LOGGER.warning("[%s] accountage %s", ctx.channel.name, resp.status_code)
            await self._notify_failure(ctx, "accountage", "查詢失敗，請稍後再試")
            return

        data = resp.json().get("data", [])
        if not data:
            if target:
                await self._ctx_reply(ctx, f"找不到使用者：{target}")
            else:
                await self._notify_failure(ctx, "accountage", "查詢失敗，請稍後再試")
            return

        user = data[0]
        created_at = datetime.fromisoformat(user["created_at"].replace("Z", "+00:00"))
        display = user.get("display_name") or user.get("login") or "?"
        await self._ctx_reply(
            ctx,
            f"@{display} 的 Twitch 帳號已建立 {_humanise_since(created_at)}"
            f"（{created_at.strftime('%Y-%m-%d')}）",
        )
        await self._record(ctx, "accountage")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(ViewerStatsComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
