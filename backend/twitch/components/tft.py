import asyncio
import json
import logging
import random
import re
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx
from twitchio.ext import commands

if TYPE_CHECKING:
    from main import Bot

LOGGER = logging.getLogger("TFTComponent")

# 段位中文映射
TIER_TRANSLATION = {
    "IRON": "鐵牌",
    "BRONZE": "銅牌",
    "SILVER": "銀牌",
    "GOLD": "金牌",
    "PLATINUM": "白金",
    "EMERALD": "翡翠",
    "DIAMOND": "鑽石",
    "MASTER": "大師",
    "GRANDMASTER": "宗師",
    "CHALLENGER": "菁英",
}


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
        """獲取 TW 排行榜數據（30 秒快取）"""
        now = time.time()

        if self._cache and (now - self._cache_time) < 30:
            LOGGER.debug("Using cached data")
            return self._cache

        if now - self._last_request < 3:
            LOGGER.info("Rate limited, using cache")
            return self._cache

        try:
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

            match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
                response.text,
                re.DOTALL
            )
            if not match:
                LOGGER.error("Data element not found, using cache")
                return self._cache

            data: dict[str, Any] = json.loads(match.group(1))[
                "props"]["pageProps"]["data"]

            self._cache = data
            self._cache_time = now
            self._last_request = now

            LOGGER.info(
                f"Fetched leaderboard - {len(data.get('entries', []))} players")
            return data

        except Exception as e:
            LOGGER.error(f"Scraping failed: {e}, using cache")
            return self._cache

    async def get_player_data(self, username: str, tag: str) -> dict[str, Any] | None:
        """獲取玩家個人資料（段位、LP、排名、最近比賽）"""
        now = time.time()
        if now - self._last_request < 3:
            await asyncio.sleep(3 - (now - self._last_request))

        try:
            await asyncio.sleep(random.uniform(0.5, 1.5))

            url = f"https://tactics.tools/player/tw/{quote(username, safe='')}/{quote(tag, safe='')}"
            LOGGER.info(f"Fetching player data from URL: {url}")

            response = await self._client.get(
                url,
                headers={
                    "User-Agent": random.choice(self._user_agents),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
                },
            )

            if response.status_code != 200:
                LOGGER.warning(f"Player page HTTP {response.status_code}")
                return None

            match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
                response.text,
                re.DOTALL
            )
            if not match:
                LOGGER.error("Player data element not found")
                return None

            page_props = json.loads(match.group(1)).get(
                "props", {}).get("pageProps", {})
            initial_data = page_props.get("initialData", {})
            player_info = initial_data.get("playerInfo", {})

            if not player_info:
                LOGGER.error(f"No playerInfo for {username}#{tag}")
                return None

            # 提取段位和 LP（格式: ["DIAMOND IV", 10]）
            ranked_league = player_info.get("rankedLeague", [])
            tier, rank_division, lp = "", "", 0
            if ranked_league and len(ranked_league) >= 2:
                parts = ranked_league[0].split()
                tier = parts[0] if parts else ""
                rank_division = parts[1] if len(parts) > 1 else ""
                lp = ranked_league[1]

            # 提取排名（格式: [排名數字, 百分比]）
            # ≤1000 顯示排名，>1000 顯示百分比
            local_rank_data = player_info.get("localRank")
            rank_position, percentile = None, None
            if local_rank_data and isinstance(local_rank_data, list) and len(local_rank_data) >= 2:
                rank_num = local_rank_data[0]
                if rank_num <= 1000:
                    rank_position = rank_num
                else:
                    percentile = local_rank_data[1] * 100

            # 提取最近比賽 LP 變化
            matches = initial_data.get("matches", [])
            last_match_lp = None
            if matches:
                lp_diff = matches[0].get("lpDiff")
                if lp_diff is not None:
                    last_match_lp = f"{'+' if lp_diff > 0 else ''}{lp_diff} LP"

            self._last_request = time.time()
            LOGGER.info(
                f"Fetched player data - {username}#{tag}: {tier} {rank_division} {lp} LP")

            return {
                "summonerName": page_props.get("playerName", username),
                "tier": tier,
                "rank": rank_division,
                "leaguePoints": lp,
                "rank_position": rank_position,
                "percentile": percentile,
                "last_match_lp": last_match_lp,
            }

        except Exception as e:
            LOGGER.error(f"Player data fetch failed: {e}")
            return None

    @commands.cooldown(rate=1, per=3)
    @commands.command(name="rk")
    async def leaderboard_command(
        self, ctx: commands.Context["Bot"], user_id: str | None = None
    ) -> None:
        """查詢 TFT 排行榜（!rk 顯示門檻，!rk 玩家名#tag 查玩家）"""
        LOGGER.debug(
            f"!rk command - {ctx.author.name} query: {user_id or 'threshold'}")

        data = await self.get_leaderboard_data()
        if not data:
            await ctx.reply("資料獲取失敗，請稍後再試")
            return

        entries = data.get("entries", [])
        thresholds = data.get("thresholds", [0, 0])

        if user_id is None:
            c_lp = thresholds[0] if thresholds else 0
            gm_lp = thresholds[1] if len(thresholds) > 1 else 0
            await ctx.reply(f"[TW] 菁英：{c_lp} LP | 宗師：{gm_lp} LP")
            return

        if "#" not in user_id:
            await ctx.reply("請使用正確格式：!rk <玩家名稱>#<tag>")
            return

        parts = user_id.split("#", 1)
        username, tag = parts[0], parts[1] if len(parts) > 1 else ""
        if not username or not tag:
            await ctx.reply("請使用正確格式：!rk <玩家名稱>#<tag>")
            return

        # 步驟 1：先從排行榜查找
        for player in entries:
            if player.get("playerName", "").lower() == user_id.lower():
                rank_num = player.get("num")
                rank_data = player.get("rank", [None, 0])
                tier = rank_data[0] if len(rank_data) > 0 else None
                lp = rank_data[1] if len(rank_data) > 1 else 0

                tier_display = TIER_TRANSLATION.get(
                    tier, tier) if tier else "未知段位"
                await ctx.reply(f"{tier_display} {lp} LP | [TW] #{rank_num}")
                LOGGER.debug(f"Query success (leaderboard) - {user_id}")
                return

        # 步驟 2：查詢個人頁面
        player_data = await self.get_player_data(username, tag)
        if player_data:
            tier = player_data.get("tier", "")
            rank_division = player_data.get("rank", "")
            lp = player_data.get("leaguePoints", 0)
            rank_position = player_data.get("rank_position")
            percentile = player_data.get("percentile")
            last_match_lp = player_data.get("last_match_lp")

            tier_cn = TIER_TRANSLATION.get(tier, tier) if tier else ""
            if tier_cn and rank_division:
                tier_display = f"{tier_cn} {rank_division}"
            elif tier_cn:
                tier_display = tier_cn
            else:
                tier_display = "未定級"

            rank_info = ""
            if rank_position:
                rank_info = f" | [TW] #{rank_position}"
            elif percentile is not None:
                rank_info = f" | [TW] 前 {percentile:.2f}%"

            lp_change_info = f" | 最近：{last_match_lp}" if last_match_lp else ""

            await ctx.reply(f"{tier_display} {lp} LP{rank_info}{lp_change_info}")
            LOGGER.debug(f"Query success (player page) - {user_id}")
            return

        await ctx.reply(f"找不到玩家：{user_id}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(LeaderboardComponent(bot))
    LOGGER.info("TFT leaderboard component loaded")


async def teardown(bot: commands.Bot) -> None:
    for component in bot._components:
        if isinstance(component, LeaderboardComponent):
            await component._client.aclose()
    LOGGER.info("TFT leaderboard component unloaded")
