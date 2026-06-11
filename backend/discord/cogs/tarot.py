import logging
import random
from datetime import UTC, datetime
from hashlib import md5

import discord
from discord import app_commands
from discord.ext import commands

from core import DATA_DIR, load_json
from core.embed_factory import EmbedFactory

LOGGER: logging.Logger = logging.getLogger(__name__)


class TarotCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._load_data()

    def _load_data(self) -> None:
        self.tarot_data = load_json(DATA_DIR / "tarot.json")
        self._embed = EmbedFactory.default()

    def _format_quote(self, text: str) -> str:
        """
        將文字按換行符拆分，並為每一行加上 Discord 的引用符號 '>'
        """
        if not text:
            return "> -"
        lines = text.split("\n")
        # 移除空行並在每行前加上引用符號
        return "\n".join([f"> {line.strip()}" for line in lines if line.strip()])

    def _get_daily_card(self, user_id: int) -> tuple[str, bool]:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        seed_string = f"{user_id}-{today}"
        seed = int(md5(seed_string.encode()).hexdigest(), 16)

        rng = random.Random(seed)
        card_ids = list(self.tarot_data["cards"].keys())
        card_id = rng.choice(card_ids)
        is_reversed = rng.choice([True, False])

        return card_id, is_reversed

    @app_commands.command(name="tarot", description="塔羅占卜")
    @app_commands.describe(category="想詢問的主題（可選）")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="綜合運勢", value="general"),
            app_commands.Choice(name="感情發展", value="love"),
            app_commands.Choice(name="事業學業", value="career"),
            app_commands.Choice(name="財務運勢", value="finance"),
        ]
    )
    async def tarot(self, interaction: discord.Interaction, category: str = "general") -> None:
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
            meaning_raw = card_info["meanings"].get(category, card_info["meanings"]["general"])
            keywords = "、".join(card_info["keywords"])
            advice_raw = card_info.get("advice", "靜心思考這張牌對你今天的意義。")

            # 格式化為 Markdown 引用
            formatted_meaning = self._format_quote(meaning_raw)
            formatted_advice = self._format_quote(advice_raw)

            color = discord.Colour(int(color_hex.lstrip("#"), 16))

            # 建立 Embed (author/footer 由 EmbedFactory 從 embed.json 套用)
            embed = self._embed.build(
                title=f"{card_name} ({orientation})",
                description=f"*{card_name_en} - {orientation_en}*",
                color=color,
                image=card_data.get("image_url"),
            )

            # 主題標籤轉換
            cat_label = {
                "general": "綜合",
                "love": "感情",
                "career": "事業",
                "finance": "財運",
            }.get(category, "綜合")

            # Field 設置
            embed.add_field(name="**關鍵字**", value=f"> {keywords}", inline=False)
            embed.add_field(name=f"**{cat_label}解析**", value=formatted_meaning, inline=False)
            embed.add_field(name="**今日建議**", value=formatted_advice, inline=False)

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            LOGGER.exception(f"Tarot command error: {e}")
            await interaction.response.send_message("塔羅牌抽取過程中發生神秘干擾", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TarotCog(bot))
