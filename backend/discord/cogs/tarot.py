"""Tarot card reading commands"""

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
        """Get a consistent daily card for a user based on date and user ID

        Returns:
            tuple[str, bool]: (card_id, is_reversed)
        """
        today = datetime.now().strftime("%Y-%m-%d")
        seed_string = f"{user_id}-{today}"
        seed = int(md5(seed_string.encode()).hexdigest(), 16)

        random.seed(seed)

        card_ids = list(self.tarot_data["cards"].keys())
        card_id = random.choice(card_ids)
        is_reversed = random.choice([True, False])

        random.seed()

        return card_id, is_reversed

    @app_commands.command(name="tarot", description="每日塔羅牌抽取")
    async def tarot(self, interaction: discord.Interaction):
        try:
            user_id = interaction.user.id
            card_id, is_reversed = self._get_daily_card(user_id)

            card_data = self.tarot_data["cards"][card_id]
            card_name = card_data["name"]
            card_name_en = card_data["name_en"]

            if is_reversed:
                orientation = "逆位"
                orientation_en = "Reversed"
                card_info = card_data["reversed"]
                color_hex = self.tarot_data["colors"]["reversed"]
            else:
                orientation = "正位"
                orientation_en = "Upright"
                card_info = card_data["upright"]
                color_hex = self.tarot_data["colors"]["upright"]

            keywords = "、".join(card_info["keywords"])
            meaning = card_info["meaning"]

            color = discord.Colour(int(color_hex.lstrip("#"), 16))

            embed = discord.Embed(
                title=f"{card_name} ({orientation})",
                description=f"*{card_name_en} - {orientation_en}*",
                color=color,
            )

            tarot_author = self.tarot_data["embed"].get("author", {})
            global_author = self.global_embed_config.get("author", {})

            author_name = tarot_author.get("name") or global_author.get("name")
            if author_name:
                author_icon = tarot_author.get("icon_url") or global_author.get("icon_url") or None
                author_url = tarot_author.get("url") or global_author.get("url") or None
                embed.set_author(
                    name=author_name,
                    icon_url=author_icon,
                    url=author_url,
                )

            # Use card-specific image as the main image
            card_image_url = card_data.get("image_url")
            if card_image_url:
                embed.set_image(url=card_image_url)

            embed.add_field(
                name="**關鍵字**",
                value=f"> {keywords}",
                inline=False
            )

            embed.add_field(
                name="**牌義解析**",
                value=f"> {meaning}",
                inline=False
            )

            embed.add_field(
                name="**今日建議**",
                value="> 靜心思考這張牌對你今天的意義，讓它的智慧引導你的決定。",
                inline=False
            )

            tarot_footer = self.tarot_data["embed"].get("footer", {})
            global_footer = self.global_embed_config.get("footer", {})

            footer_text = tarot_footer.get("text") or global_footer.get("text")
            if footer_text:
                footer_icon = tarot_footer.get("icon_url") or global_footer.get("icon_url") or None
                embed.set_footer(text=footer_text, icon_url=footer_icon)

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(
                f"塔羅牌抽取過程中發生神秘干擾: {e}", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Tarot(bot))
