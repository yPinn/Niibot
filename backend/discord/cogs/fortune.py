"""
運勢功能 Cog
提供今日運勢占卜
"""

import json
import random
from datetime import datetime

from config import DATA_DIR
from discord.ext import commands

import discord
from discord import app_commands


class Fortune(commands.Cog):
    """運勢功能指令"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._load_data()

    def _load_data(self):
        """載入運勢和全域 Embed 數據"""
        # 載入運勢數據（包含專屬 embed 配置）
        with open(DATA_DIR / "fortune.json", "r", encoding="utf-8") as f:
            self.fortune_data = json.load(f)

        # 載入全域 Embed 配置
        with open(DATA_DIR / "embed.json", "r", encoding="utf-8") as f:
            self.global_embed_config = json.load(f)

    def _get_fortune_level(self, date_modifier: float = 1.0) -> str:
        """根據權重隨機選擇運勢等級"""
        levels = list(self.fortune_data["fortune_levels"].keys())
        weights = [
            self.fortune_data["fortune_levels"][level]["weight"] * date_modifier
            for level in levels
        ]
        result = random.choices(levels, weights=weights, k=1)[0]
        return str(result)

    def _get_date_bonus(self) -> tuple[str | None, float]:
        """檢查今日特殊日期加成"""
        today = datetime.now()
        date_key = f"{today.month}-{today.day}"

        special_dates = self.fortune_data.get("special_dates", {})
        if date_key in special_dates:
            event = special_dates[date_key]
            return event["name"], event["modifier"]
        return None, 1.0

    @app_commands.command(name="fortune", description="今日運勢")
    async def fortune(self, interaction: discord.Interaction):
        """查看今日運勢"""
        try:
            # 獲取特殊日期加成
            special_event, date_modifier = self._get_date_bonus()

            # 獲取運勢等級
            fortune_level = self._get_fortune_level(date_modifier)
            level_data = self.fortune_data["fortune_levels"][fortune_level]
            category = level_data["category"]
            description = level_data["description"]

            # 獲取各項運勢詳情
            fortune_details = self.fortune_data["fortune_details"][category]
            career = random.choice(fortune_details["事業"])
            wealth = random.choice(fortune_details["財運"])
            love = random.choice(fortune_details["愛情"])
            health = random.choice(fortune_details["健康"])

            # 獲取宜忌建議
            advice_data = self.fortune_data["advice"]
            good_advice = random.choice(advice_data["宜"][category])
            avoid_advice = random.choice(advice_data["忌"][category])

            # 獲取幸運元素
            lucky_data = self.fortune_data["lucky_elements"][category]
            lucky_color = random.choice(lucky_data["colors"])
            lucky_number = random.choice(lucky_data["numbers"])
            lucky_hour = random.choice(lucky_data["hours"])

            # 根據運勢等級選擇顏色
            color_map: dict[str, discord.Colour] = {
                "好": discord.Colour.gold(),
                "中": discord.Colour.blue(),
                "差": discord.Colour.dark_gray(),  # type: ignore[misc]
            }

            # 建立 Embed
            embed = discord.Embed(
                title=f"今日運勢【{fortune_level}】",
                description=f"{description}",
                color=color_map.get(category, discord.Colour.purple()),
            )

            # 設定 author - 優先使用 fortune 專屬設定，否則使用全域設定
            fortune_author = self.fortune_data["embed"].get("author", {})
            global_author = self.global_embed_config.get("author", {})

            author_name = fortune_author.get("name") or global_author.get("name")
            if author_name:
                author_icon = fortune_author.get("icon_url") or global_author.get("icon_url") or None
                author_url = fortune_author.get("url") or global_author.get("url") or None
                embed.set_author(
                    name=author_name,
                    icon_url=author_icon,
                    url=author_url,
                )

            # 設定 thumbnail (酥烤貓圖片)
            thumbnail_url = self.fortune_data["embed"].get("thumbnail")
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)

            # 設定 image (只有運勢「好」才顯示大圖)
            if category == "好":
                image_url = self.fortune_data["embed"].get("image")
                if image_url:
                    embed.set_image(url=image_url)

            # 特殊日期提示
            if special_event:
                embed.add_field(
                    name="🎊 特殊加成",
                    value=f"今日是 **{special_event}**，運勢有額外加成！",
                    inline=False,
                )

            # 各項運勢 (兩兩一行)
            embed.add_field(name="📊 | 事業運", value=career, inline=False)
            embed.add_field(name="💰 | 財　運", value=wealth, inline=False)
            embed.add_field(name="💕 | 愛情運", value=love, inline=False)
            embed.add_field(name="💪 | 健康運", value=health, inline=False)

            # 幸運元素
            embed.add_field(
                name="🎨 幸運元素",
                value=f"**顏色:** {lucky_color}\n**數字:** {lucky_number}\n**時辰:** {lucky_hour}",
                inline=False,
            )

            # 宜忌建議
            embed.add_field(name="✅ 宜", value=good_advice, inline=True)
            embed.add_field(name="⛔ 忌", value=avoid_advice, inline=True)

            # 設定 footer - 優先使用 fortune 專屬設定，否則使用全域設定
            fortune_footer = self.fortune_data["embed"].get("footer", {})
            global_footer = self.global_embed_config.get("footer", {})

            footer_text = fortune_footer.get("text") or global_footer.get("text")
            if footer_text:
                footer_icon = fortune_footer.get("icon_url") or global_footer.get("icon_url") or None
                embed.set_footer(text=footer_text, icon_url=footer_icon)

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(
                f"占卜過程中發生神秘干擾: {e}", ephemeral=True
            )


async def setup(bot: commands.Bot):
    """載入 Cog"""
    await bot.add_cog(Fortune(bot))
