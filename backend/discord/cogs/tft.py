"""TFT 戰棋排行榜查詢 Cog"""

import asyncio
import json
import logging
import random
import re
import time
from datetime import UTC
from typing import Any
from urllib.parse import quote

import discord
import httpx
from config import DATA_DIR
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("discord_bot.tft")

# 段位中文映射
TIER_TRANSLATION = {
    "IRON": "鐵",
    "BRONZE": "銅",
    "SILVER": "銀",
    "GOLD": "金",
    "PLATINUM": "白金",
    "EMERALD": "翡翠",
    "DIAMOND": "鑽石",
    "MASTER": "大師",
    "GRANDMASTER": "宗師",
    "CHALLENGER": "菁英",
}

# 段位圖片 URL（Riot 官方 CDN）
TIER_IMAGES = {
    "IRON": "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/iron.png",
    "BRONZE": "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/bronze.png",
    "SILVER": "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/silver.png",
    "GOLD": "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/gold.png",
    "PLATINUM": "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/platinum.png",
    "EMERALD": "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/emerald.png",
    "DIAMOND": "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/diamond.png",
    "MASTER": "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/master.png",
    "GRANDMASTER": "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/grandmaster.png",
    "CHALLENGER": "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/challenger.png",
}


class TFT(commands.Cog):
    """TFT 戰棋排行榜查詢"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_request = 0.0
        self._cache: dict[str, Any] | None = None
        self._cache_time = 0.0
        self._client = httpx.AsyncClient(timeout=10.0)

        self._user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        ]

        self._load_embed_config()

    def _load_embed_config(self) -> None:
        """載入全域 embed 配置"""
        try:
            with open(DATA_DIR / "embed.json", encoding="utf-8") as f:
                self.global_embed_config = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load embed config: {e}")
            self.global_embed_config = {}

    async def cog_unload(self) -> None:
        """Cog 卸載時關閉 HTTP 客戶端"""
        await self._client.aclose()

    async def get_leaderboard_data(self) -> dict[str, Any] | None:
        """獲取 TW 排行榜數據（30 秒快取）"""
        now = time.time()

        if self._cache and (now - self._cache_time) < 30:
            logger.debug("Using cached leaderboard data")
            return self._cache

        if now - self._last_request < 3:
            logger.info("Rate limited, using cache")
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
                logger.warning(f"HTTP {response.status_code}, using cache")
                return self._cache

            match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
                response.text,
                re.DOTALL,
            )
            if not match:
                logger.error("Data element not found")
                return self._cache

            data: dict[str, Any] = json.loads(match.group(1))["props"]["pageProps"]["data"]

            self._cache = data
            self._cache_time = now
            self._last_request = now

            logger.info(f"Fetched leaderboard - {len(data.get('entries', []))} players")
            return data

        except Exception as e:
            logger.error(f"Leaderboard fetch failed: {e}")
            return self._cache

    async def _fetch_player_data(self, username: str, tag: str) -> dict[str, Any] | None:
        """實際執行玩家資料爬取"""
        now = time.time()
        if now - self._last_request < 3:
            await asyncio.sleep(3 - (now - self._last_request))

        try:
            await asyncio.sleep(random.uniform(0.5, 1.5))

            url = (
                f"https://tactics.tools/player/tw/{quote(username, safe='')}/{quote(tag, safe='')}"
            )
            logger.info(f"Fetching player: {username}#{tag}")

            response = await self._client.get(
                url,
                headers={
                    "User-Agent": random.choice(self._user_agents),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
                },
            )

            if response.status_code != 200:
                logger.warning(f"Player page HTTP {response.status_code}")
                return None

            match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
                response.text,
                re.DOTALL,
            )
            if not match:
                logger.error("Player data not found")
                return None

            page_props = json.loads(match.group(1)).get("props", {}).get("pageProps", {})
            initial_data = page_props.get("initialData", {})
            player_info = initial_data.get("playerInfo", {})

            if not player_info:
                return None

            ranked_league = player_info.get("rankedLeague", [])
            tier, rank_division, lp = "", "", 0
            if ranked_league and len(ranked_league) >= 2:
                parts = ranked_league[0].split()
                tier = parts[0] if parts else ""
                # 高段位沒有分級（MASTER/GRANDMASTER/CHALLENGER）
                if tier not in ["MASTER", "GRANDMASTER", "CHALLENGER"]:
                    rank_division = parts[1] if len(parts) > 1 else ""
                lp = ranked_league[1]

            local_rank_data = player_info.get("localRank")
            rank_position, percentile = None, None
            if local_rank_data and isinstance(local_rank_data, list) and len(local_rank_data) >= 2:
                rank_num = local_rank_data[0] + 1  # API 回傳 0-indexed，需 +1
                percentile_value = local_rank_data[1] * 100
                if rank_num <= 1000:
                    rank_position = rank_num
                percentile = percentile_value

            matches = initial_data.get("matches", [])
            last_match_lp = None
            last_match_time = None
            if matches:
                match_data = matches[0]
                lp_diff = match_data.get("lpDiff")
                if lp_diff is not None:
                    last_match_lp = lp_diff

                timestamp = match_data.get("dateTime")
                if timestamp:
                    last_match_time = timestamp

            self._last_request = time.time()

            return {
                "summonerName": page_props.get("playerName", username),
                "tier": tier,
                "rank": rank_division,
                "leaguePoints": lp,
                "rank_position": rank_position,
                "percentile": percentile,
                "last_match_lp": last_match_lp,
                "last_match_time": last_match_time,
            }

        except Exception as e:
            logger.error(f"Player fetch failed: {e}")
            return None

    async def get_player_data(self, username: str, tag: str) -> dict[str, Any] | None:
        """獲取玩家個人資料（智能雙重查詢：資料>24小時自動重新爬取）"""
        data = await self._fetch_player_data(username, tag)

        if not data:
            return None

        if data.get("last_match_time"):
            now = time.time()
            timestamp_sec = data["last_match_time"] / 1000
            age_hours = (now - timestamp_sec) / 3600

            if age_hours > 24:
                logger.info(f"Data is {age_hours:.1f} hours old, re-fetching after 3s...")
                await asyncio.sleep(3)
                fresh_data = await self._fetch_player_data(username, tag)
                if fresh_data:
                    return fresh_data

        return data

    @app_commands.command(name="tft", description="TFT 排名")
    @app_commands.describe(player="玩家名稱（格式：玩家名稱#TAG，留空則顯示門檻）")
    async def tft_command(
        self, interaction: discord.Interaction, player: str | None = None
    ) -> None:
        """TFT 排行榜查詢指令"""
        await interaction.response.defer()

        if player:
            await self._show_player(interaction, player)
        else:
            await self._show_threshold(interaction)

    async def _show_threshold(self, interaction: discord.Interaction) -> None:
        """顯示排行榜門檻"""
        data = await self.get_leaderboard_data()
        if not data:
            await interaction.followup.send("資料獲取失敗，請稍後再試", ephemeral=True)
            return

        thresholds = data.get("thresholds", [0, 0])
        c_lp = thresholds[0] if thresholds else 0
        gm_lp = thresholds[1] if len(thresholds) > 1 else 0

        embed = discord.Embed(title="伺服器排行榜 [TW]", color=discord.Color.gold())

        embed.add_field(name="菁英", value=f"> **{c_lp:,} LP**", inline=False)
        embed.add_field(name="宗師", value=f"> **{gm_lp:,} LP**", inline=False)

        global_author = self.global_embed_config.get("author", {})
        if global_author.get("name"):
            embed.set_author(name=global_author.get("name"), icon_url=global_author.get("icon_url"))

        embed.set_footer(text="數據來源: tactics.tools")
        embed.set_thumbnail(url=TIER_IMAGES.get("CHALLENGER"))

        await interaction.followup.send(embed=embed)

    async def _show_player(self, interaction: discord.Interaction, player_input: str) -> None:
        """顯示玩家資料"""
        if "#" not in player_input:
            await interaction.followup.send("請使用正確格式：玩家名稱#TAG", ephemeral=True)
            return

        parts = player_input.split("#", 1)
        username, tag = parts[0], parts[1] if len(parts) > 1 else ""

        if not username or not tag:
            await interaction.followup.send("請使用正確格式：玩家名稱#TAG", ephemeral=True)
            return

        player_data = await self.get_player_data(username, tag)
        if player_data:
            await self._send_player_embed(interaction, player_data, player_input, username, tag)
        else:
            await interaction.followup.send(f"找不到玩家：{player_input}", ephemeral=True)

    async def _send_player_embed(
        self,
        interaction: discord.Interaction,
        player_data: dict[str, Any],
        player_input: str,
        username: str,
        tag: str,
    ) -> None:
        """發送玩家資料 Embed"""
        from datetime import datetime
        from urllib.parse import quote

        tier = player_data.get("tier", "")
        rank_division = player_data.get("rank", "")
        lp = player_data.get("leaguePoints", 0)
        rank_position = player_data.get("rank_position")
        percentile = player_data.get("percentile")
        last_match_lp = player_data.get("last_match_lp")
        last_match_time = player_data.get("last_match_time")

        tier_cn = TIER_TRANSLATION.get(tier, tier) if tier else ""
        if tier_cn and rank_division:
            tier_display = f"{tier_cn} {rank_division}"
        elif tier_cn:
            tier_display = tier_cn
        else:
            tier_display = "未定級"

        formatted_name = player_input.replace("#", " #")

        embed = discord.Embed(title=formatted_name, color=discord.Color.blue())

        embed.add_field(name="段位", value=f"> {tier_display} **{lp:,} LP**", inline=False)

        # 排名顯示：≤1000 顯示數字，否則顯示百分位
        if rank_position is not None and rank_position <= 1000:
            rank_value = f"> **#{rank_position}**"
        elif percentile is not None:
            rank_value = f"> 前 **{percentile:.2f}%**"
        else:
            rank_value = "> 未排名"

        embed.add_field(name="排名", value=rank_value, inline=False)
        if last_match_lp is not None:
            lp_sign = "+" if last_match_lp > 0 else ""
            match_value = f"**{lp_sign}{last_match_lp} LP**"

            if last_match_time:
                try:
                    timestamp_sec = (
                        last_match_time / 1000 if last_match_time > 1e10 else last_match_time
                    )
                    match_datetime = datetime.fromtimestamp(timestamp_sec, tz=UTC)
                    now = datetime.now(UTC)
                    time_diff = now - match_datetime

                    if time_diff.days > 0:
                        time_ago = f"{time_diff.days}天前"
                    elif time_diff.seconds >= 3600:
                        hours = time_diff.seconds // 3600
                        time_ago = f"{hours}小時前"
                    elif time_diff.seconds >= 60:
                        minutes = time_diff.seconds // 60
                        time_ago = f"{minutes}分鐘前"
                    else:
                        time_ago = "剛剛"

                    match_value = f"**{lp_sign}{last_match_lp} LP** ({time_ago})"
                except Exception as e:
                    logger.debug(f"Failed to parse match time: {e}")
        else:
            match_value = "無資料"

        embed.add_field(name="最近比賽", value=f"> {match_value}", inline=False)

        global_author = self.global_embed_config.get("author", {})
        if global_author.get("name"):
            embed.set_author(name=global_author.get("name"), icon_url=global_author.get("icon_url"))

        embed.set_footer(text="數據來源: tactics.tools")

        tier_image = TIER_IMAGES.get(tier)
        if tier_image:
            embed.set_thumbnail(url=tier_image)

        player_url = (
            f"https://tactics.tools/player/tw/{quote(username, safe='')}/{quote(tag, safe='')}"
        )
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(label="詳細資料", url=player_url, style=discord.ButtonStyle.link)
        )

        await interaction.followup.send(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TFT(bot))
    logger.info("TFT cog loaded")
