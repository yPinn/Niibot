"""Twitch interactive game commands: !roll (shared chamber roulette), !choose."""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING

import httpx
from twitchio.ext import commands

from core.component import BotComponent
from core.guards import check_command
from shared.repositories.command_config import CommandConfigRepository

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER: logging.Logger = logging.getLogger(__name__)

_TOTAL_CHAMBERS = 6
_ROULETTE_TIMEOUT = 60
_MAX_OPTIONS = 20


class _ChamberState:
    """Shared per-channel revolver state.

    Bullet is placed at a random position on init; pulls advance sequentially.
    Guaranteed to hit within _TOTAL_CHAMBERS pulls.
    """

    def __init__(self) -> None:
        self.remaining: int = _TOTAL_CHAMBERS
        self._bullet_at: int = random.randint(1, _TOTAL_CHAMBERS)
        self._pulled: int = 0

    def pull(self) -> bool:
        """Advance one chamber. Returns True if bullet is hit."""
        self._pulled += 1
        self.remaining -= 1
        return self._pulled == self._bullet_at


class GamesComponent(BotComponent):
    COMMANDS: list[dict] = [
        {"command_name": "roll", "cooldown": 5, "aliases": "輪盤"},
        {"command_name": "choose", "cooldown": 5, "aliases": "選擇"},
    ]

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self.cmd_repo = CommandConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.channel_repo = self.bot.channels  # type: ignore[attr-defined]
        self._chambers: dict[str, _ChamberState] = {}

    def refresh_pool(self, pool) -> None:
        self.cmd_repo.pool = pool

    def _get_chamber(self, channel_id: str) -> _ChamberState:
        if channel_id not in self._chambers:
            self._chambers[channel_id] = _ChamberState()
        return self._chambers[channel_id]

    @commands.command(name="roll", aliases=["輪盤"])
    async def roll(self, ctx: commands.Context[Bot]) -> None:
        """聊天室共用輪盤，中彈 timeout 60 秒。"""
        config = await check_command(self.cmd_repo, ctx, "roll", self.channel_repo)
        if not config:
            return

        channel_id = ctx.broadcaster.id

        if ctx.chatter.broadcaster:  # type: ignore[attr-defined]
            await self._ctx_reply(ctx, "狼人不能下場玩 ImTyping")
            return

        chamber = self._get_chamber(channel_id)
        hit = chamber.pull()

        if not hit:
            await self._ctx_reply(ctx, "你平安度過今晚 BloodTrail")
            return

        self._chambers[channel_id] = _ChamberState()
        await self._ctx_reply(ctx, "你被狼人選中，出局 ResidentSleeper")

        if channel_id not in self.bot._bot_is_mod:
            LOGGER.warning("[%s] Roulette: bot is not mod, cannot timeout", channel_id)
            return

        token_obj = await self.channel_repo.get_token(self.bot._bot_id, "bot")
        if not token_obj:
            LOGGER.warning("[%s] Roulette: no bot token found", channel_id)
            return

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.twitch.tv/helix/moderation/bans",
                    headers={
                        "Client-Id": self.bot._client_id,
                        "Authorization": f"Bearer {token_obj.token}",
                        "Content-Type": "application/json",
                    },
                    params={
                        "broadcaster_id": channel_id,
                        "moderator_id": self.bot._bot_id,
                    },
                    json={
                        "data": {
                            "user_id": ctx.chatter.id,
                            "duration": _ROULETTE_TIMEOUT,
                            "reason": "天亮了，你昨晚被狼人帶走了",
                        }
                    },
                )
            if resp.status_code not in (200, 204):
                LOGGER.warning(
                    "[%s] Roulette timeout failed: %s %s",
                    channel_id,
                    resp.status_code,
                    resp.text,
                )
        except Exception:
            LOGGER.exception("[%s] Roulette timeout error", channel_id)

    @commands.command(name="choose", aliases=["選擇"])
    async def choose(self, ctx: commands.Context[Bot], *, args: str | None = None) -> None:
        """從選項中隨機選一個。

        用法:
            !choose 紅 藍 綠
            !選擇 pizza hamburger sushi
        """
        config = await check_command(self.cmd_repo, ctx, "choose", self.channel_repo)
        if not config:
            return

        if not args or not args.strip():
            await self._ctx_reply(ctx, "用法：!choose 選項1 選項2 ...")
            return

        options = [o for o in args.split() if o]
        if len(options) < 2:
            await self._ctx_reply(ctx, "至少給我兩個選項！")
            return
        if len(options) > _MAX_OPTIONS:
            await self._ctx_reply(ctx, f"選項最多 {_MAX_OPTIONS} 個")
            return

        picked = random.choice(options)
        user = ctx.chatter.display_name or ctx.chatter.name
        await self._ctx_reply(ctx, f"🎯 {user} 的選擇：{picked}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(GamesComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
