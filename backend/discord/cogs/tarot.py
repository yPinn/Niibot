import json
import random
from datetime import datetime
from hashlib import md5

from config import DATA_DIR
from discord.ext import commands

import discord
from discord import app_commands


class Tarot(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._load_data()

    def _load_data(self):
        with open(DATA_DIR / "tarot.json", "r", encoding="utf-8") as f:
            self.tarot_data = json.load(f)
        with open(DATA_DIR / "embed.json", "r", encoding="utf-8") as f:
            self.global_embed_config = json.load(f)

    def _get_daily_card(self, user_id: int) -> tuple[str, bool]:
        today = datetime.now().strftime("%Y-%m-%d")
        seed_string = f"{user_id}-{today}"
        seed = int(md5(seed_string.encode()).hexdigest(), 16)

        random.seed(seed)
        card_ids = list(self.tarot_data["cards"].keys())
        card_id = random.choice(card_ids)
        is_reversed = random.choice([True, False])
        random.seed()

        return card_id, is_reversed

    @app_commands.command(name="tarot", description="每日塔羅")
    @app_commands.describe(category="想詢問的主題（可選）")
    @app_commands.choices(category=[
        app_commands.Choice(name="綜合運勢", value="general"),
        app_commands.Choice(name="感情發展", value="love"),
        app_commands.Choice(name="事業學業", value="career"),
    ])
    async def tarot(self, interaction: discord.Interaction, category: str = "general"):
        try:
            user_id = interaction.user.id
            card_id, is_reversed = self._get_daily_card(user_id)

            card_data = self.tarot_data["cards"][card_id]
            card_name = card_data["name"]
            card_name_en = card_data["name_en"]

            # 判斷正逆位與對應色彩
            if is_reversed:
                orientation, orientation_en = "逆位", "Reversed"
                card_info = card_data["reversed"]
                color_hex = self.tarot_data["colors"]["reversed"]
            else:
                orientation, orientation_en = "正位", "Upright"
                card_info = card_data["upright"]
                color_hex = self.tarot_data["colors"]["upright"]

            # 抓取對應主題的牌義 (如果主題不存在則回退到綜合解析)
            meaning = card_info["meanings"].get(
                category, card_info["meanings"]["general"])
            keywords = "、".join(card_info["keywords"])
            advice = card_info.get("advice", "靜心思考這張牌對你今天的意義。")

            color = discord.Colour(int(color_hex.lstrip("#"), 16))

            # 建立 Embed
            embed = discord.Embed(
                title=f"{card_name} ({orientation})",
                description=f"*{card_name_en} - {orientation_en}*",
                color=color,
            )

            # 作者資訊處理
            tarot_author = self.tarot_data["embed"].get("author", {})
            global_author = self.global_embed_config.get("author", {})
            author_name = tarot_author.get("name") or global_author.get("name")
            if author_name:
                embed.set_author(
                    name=author_name,
                    icon_url=tarot_author.get(
                        "icon_url") or global_author.get("icon_url"),
                    url=tarot_author.get("url") or global_author.get("url")
                )

            # 設置牌面圖片
            if card_data.get("image_url"):
                embed.set_image(url=card_data["image_url"])

            # 主題標籤轉換
            cat_label = {"general": "綜合", "love": "感情",
                         "career": "事業"}.get(category, "綜合")

            embed.add_field(
                name="**關鍵字**", value=f"> {keywords}", inline=False)
            embed.add_field(name=f"**{cat_label}解析**",
                            value=f"> {meaning}", inline=False)
            embed.add_field(name="**今日建議**", value=f"> {advice}", inline=False)

            # 頁尾資訊處理
            tarot_footer = self.tarot_data["embed"].get("footer", {})
            global_footer = self.global_embed_config.get("footer", {})
            footer_text = tarot_footer.get("text") or global_footer.get("text")
            if footer_text:
                embed.set_footer(
                    text=footer_text,
                    icon_url=tarot_footer.get(
                        "icon_url") or global_footer.get("icon_url")
                )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(
                f"塔羅牌抽取過程中發生神秘干擾: {e}", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Tarot(bot))
