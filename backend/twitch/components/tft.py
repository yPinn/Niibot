import asyncio
import json
import logging
import random
import re
import time
from typing import TYPE_CHECKING, Any

import httpx
from twitchio.ext import commands

if TYPE_CHECKING:
    from main import Bot

LOGGER = logging.getLogger("TFTComponent")


class LeaderboardComponent(commands.Component):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._last_request = 0.0
        self._cache: dict[str, Any] | None = None
        self._cache_time = 0.0
        self._client = httpx.AsyncClient(timeout=8.0)

        self._user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        ]

    async def get_leaderboard_data(self) -> dict[str, Any] | None:
        """獲取排行榜數據（異步）"""
        now = time.time()

        # 檢查 30 秒快取
        if self._cache and (now - self._cache_time) < 30:
            LOGGER.debug("Using cached data")
            return self._cache

        # 頻率限制：3 秒間隔
        if now - self._last_request < 3:
            LOGGER.info("Rate limited, using cache")
            return self._cache

        try:
            # 異步隨機延遲
            await asyncio.sleep(random.uniform(0.5, 1.5))

            response = await self._client.get(
                "https://tactics.tools/leaderboards/tw",
                headers={
                    "User-Agent": random.choice(self._user_agents),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
                },
            )

            if response.status_code != 200:
                LOGGER.warning(f"HTTP {response.status_code}, using cache")
                return self._cache

            # 使用 regex 直接提取 __NEXT_DATA__ (比 BeautifulSoup 快 10x)
            match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
                response.text,
                re.DOTALL
            )
            if not match:
                LOGGER.error("Data element not found, using cache")
                return self._cache

            data: dict[str, Any] = json.loads(match.group(1))["props"]["pageProps"]["data"]

            # 更新快取
            self._cache = data
            self._cache_time = now
            self._last_request = now

            entries_count = len(data.get("entries", []))
            LOGGER.info(f"Fetched leaderboard - {entries_count} players")
            return data

        except Exception as e:
            LOGGER.error(f"Scraping failed: {e}, using cache")
            return self._cache

    @commands.cooldown(rate=1, per=3)
    @commands.command(name="rk")
    async def leaderboard_command(
        self, ctx: commands.Context["Bot"], user_id: str | None = None
    ) -> None:
        """查詢 TFT 排行榜

        用法:
            !rk - 顯示挑戰者和宗師門檻
            !rk <玩家名稱> - 查詢特定玩家排名
        """
        LOGGER.debug(f"!rk command - {ctx.author.name} query: {user_id or 'threshold'}")

        data = await self.get_leaderboard_data()

        if not data:
            await ctx.reply("資料獲取失敗，請稍後再試")
            return

        entries = data.get("entries", [])
        thresholds = data.get("thresholds", [0, 0])

        # 無參數：顯示門檻
        if user_id is None:
            c_lp = thresholds[0] if thresholds else 0
            gm_lp = thresholds[1] if len(thresholds) > 1 else 0
            await ctx.reply(f"[TW] 挑戰者：{c_lp} LP，宗師：{gm_lp} LP")
            return

        # 查找玩家
        for player in entries:
            if player.get("playerName", "").lower() == user_id.lower():
                rank = player.get("num")
                lp = player.get("rank", [None, 0])[1]
                await ctx.reply(f"{user_id}：{lp} LP #{rank} [TW]")
                LOGGER.debug(f"Query success - {user_id}: {lp} LP #{rank}")
                return

        await ctx.reply(f"該玩家未上榜：{user_id}！")


async def setup(bot: commands.Bot) -> None:
    component = LeaderboardComponent(bot)
    await bot.add_component(component)
    LOGGER.info("TFT leaderboard component loaded")


async def teardown(bot: commands.Bot) -> None:
    # 關閉 httpx client
    components = [c for c in bot._components if isinstance(c, LeaderboardComponent)]
    for component in components:
        await component._client.aclose()
    LOGGER.info("TFT leaderboard component unloaded")
