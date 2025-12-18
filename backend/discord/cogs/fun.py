"""
娛樂功能 Cog
提供趣味指令
"""

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from discord.ext import commands

import discord
from discord import app_commands, ui


class EightBallModal(ui.Modal, title="神奇8號球"):
    """8號球問題輸入 Modal"""

    question: Any = ui.TextInput(
        label="你的問題",
        placeholder="輸入你想問的問題...",
        max_length=200,
    )

    async def on_submit(self, interaction: discord.Interaction):
        responses = [
            "毫無疑問",
            "當然可以",
            "絕對是的",
            "你可以相信",
            "看起來不錯",
            "很有可能",
            "前景良好",
            "是的",
            "跡象指向是",
            "回覆模糊，再試一次",
            "稍後再問",
            "現在最好不要告訴你",
            "現在無法預測",
            "集中精神再問一次",
            "別指望了",
            "我的回答是不",
            "我的消息來源說不",
            "前景不太好",
            "非常可疑",
        ]

        answer = random.choice(responses)
        embed = discord.Embed(title="神奇8號球", color=discord.Color.blue())
        embed.add_field(name="問題", value=self.question.value, inline=False)
        embed.add_field(name="答案", value=answer, inline=False)

        await interaction.response.send_message(embed=embed)


class RPSView(ui.View):
    """猜拳遊戲 Button View"""

    def __init__(self):
        super().__init__(timeout=60)

    @ui.button(label="石頭", style=discord.ButtonStyle.secondary, emoji="🪨")
    async def rock(self, interaction: discord.Interaction, button: ui.Button):
        await self.play_rps(interaction, "石頭")

    @ui.button(label="剪刀", style=discord.ButtonStyle.secondary, emoji="✂️")
    async def scissors(self, interaction: discord.Interaction, button: ui.Button):
        await self.play_rps(interaction, "剪刀")

    @ui.button(label="布", style=discord.ButtonStyle.secondary, emoji="📄")
    async def paper(self, interaction: discord.Interaction, button: ui.Button):
        await self.play_rps(interaction, "布")

    async def play_rps(self, interaction: discord.Interaction, choice: str):
        bot_choice = random.choice(["石頭", "剪刀", "布"])

        if choice == bot_choice:
            result = "平手"
            color = discord.Color.gold()
        elif (
            (choice == "石頭" and bot_choice == "剪刀")
            or (choice == "剪刀" and bot_choice == "布")
            or (choice == "布" and bot_choice == "石頭")
        ):
            result = "你贏了"
            color = discord.Color.green()
        else:
            result = "你輸了"
            color = discord.Color.red()

        embed = discord.Embed(title="猜拳遊戲", color=color)
        embed.add_field(name="你的選擇", value=choice, inline=True)
        embed.add_field(name="Bot 的選擇", value=bot_choice, inline=True)
        embed.add_field(name="結果", value=result, inline=False)

        await interaction.response.edit_message(embed=embed, view=RPSView())


class CoinFlipView(ui.View):
    """擲硬幣 Button View"""

    def __init__(self):
        super().__init__(timeout=60)

    @ui.button(label="再擲一次", style=discord.ButtonStyle.primary)
    async def flip_again(self, interaction: discord.Interaction, button: ui.Button):
        result = random.choice(["正面", "反面"])
        embed = discord.Embed(title="擲硬幣", color=discord.Color.blue())
        embed.add_field(name="結果", value=result, inline=False)

        await interaction.response.edit_message(embed=embed, view=CoinFlipView())


class Fun(commands.Cog):
    """娛樂功能指令"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._load_data()

    def _load_data(self):
        """載入所有數據檔案"""
        data_dir = Path(__file__).parent.parent.parent / "data"

        # 載入運勢數據
        with open(data_dir / "fortunes.json", "r", encoding="utf-8") as f:
            self.fortune_data = json.load(f)

        # 載入 Embed 配置
        with open(data_dir / "embed.json", "r", encoding="utf-8") as f:
            self.embed_config = json.load(f)

    def _get_fortune_level(self, date_modifier: float = 1.0) -> str:
        """根據權重隨機選擇運勢等級"""
        levels = list(self.fortune_data["fortune_levels"].keys())
        weights = [
            self.fortune_data["fortune_levels"][level]["weight"] *
            date_modifier
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

    @app_commands.command(name="roll", description="擲骰子")
    @app_commands.describe(sides="骰子面數")
    async def roll(self, interaction: discord.Interaction, sides: int = 6):
        """擲骰子"""
        if sides < 2:
            await interaction.response.send_message("骰子至少要有 2 面", ephemeral=True)
            return

        result = random.randint(1, sides)
        await interaction.response.send_message(f"擲出了 {result} 點（D{sides}）")

    @app_commands.command(name="choose", description="隨機選擇")
    @app_commands.describe(options="選項（用空格分隔）")
    async def choose(self, interaction: discord.Interaction, options: str):
        """從選項中隨機選擇"""
        choices = options.split()
        if len(choices) < 2:
            await interaction.response.send_message("請提供至少 2 個選項", ephemeral=True)
            return

        result = random.choice(choices)
        await interaction.response.send_message(f"我選擇: {result}")

    @app_commands.command(name="8ball", description="神奇8號球")
    async def eight_ball(self, interaction: discord.Interaction):
        """神奇8號球"""
        await interaction.response.send_modal(EightBallModal())

    @app_commands.command(name="coinflip", description="擲硬幣")
    async def coinflip(self, interaction: discord.Interaction):
        """擲硬幣"""
        result = random.choice(["正面", "反面"])
        embed = discord.Embed(title="擲硬幣", color=discord.Color.blue())
        embed.add_field(name="結果", value=result, inline=False)

        await interaction.response.send_message(embed=embed, view=CoinFlipView())

    @app_commands.command(name="rps", description="猜拳遊戲")
    async def rock_paper_scissors(self, interaction: discord.Interaction):
        """猜拳遊戲"""
        embed = discord.Embed(
            title="猜拳遊戲",
            description="點擊下方按鈕選擇你的出拳",
            color=discord.Color.blue(),
        )

        await interaction.response.send_message(embed=embed, view=RPSView())

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
                # timestamp=datetime.now(),
            )

            # 設定 author (Niibot - 統一發送者)
            author_data = self.embed_config.get("author", {})
            if author_data.get("name"):
                embed.set_author(
                    name=author_data.get("name"),
                    icon_url=author_data.get("icon_url"),
                    url=author_data.get("url") or None,
                )

            # 設定 thumbnail (酥烤貓圖片)
            thumbnail_url = self.embed_config.get(
                "thumbnail", {}).get("fortune")
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)

            # 設定 image (只有運勢「好」才顯示大圖)
            if category == "好":
                image_url = self.embed_config.get("image", {}).get("fortune")
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

            # 設定 footer (可選)
            footer_data = self.embed_config.get("footer", {})
            footer_text = footer_data.get("text")
            footer_icon = footer_data.get("icon_url")
            if footer_text:
                embed.set_footer(text=footer_text,
                                 icon_url=footer_icon or None)

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(
                f"占卜過程中發生神秘干擾: {e}", ephemeral=True
            )


async def setup(bot: commands.Bot):
    """載入 Cog"""
    await bot.add_cog(Fun(bot))
