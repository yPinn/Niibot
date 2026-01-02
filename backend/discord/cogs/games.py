"""Interactive game commands"""

import json
import random
from typing import Any

from config import DATA_DIR
from discord.ext import commands

import discord
from discord import app_commands, ui


class EightBallModal(ui.Modal, title="神奇8號球"):
    question: Any = ui.TextInput(
        label="你的問題",
        placeholder="輸入你想問的問題...",
        max_length=200,
    )

    def __init__(self, responses: list[str]):
        super().__init__()
        self.responses = responses

    async def on_submit(self, interaction: discord.Interaction):
        answer = random.choice(self.responses)
        embed = discord.Embed(title="神奇8號球", color=discord.Color.blue())
        embed.add_field(name="問題", value=self.question.value, inline=False)
        embed.add_field(name="答案", value=answer, inline=False)

        await interaction.response.send_message(embed=embed)


class RPSView(ui.View):
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
    def __init__(self):
        super().__init__(timeout=60)

    @ui.button(label="再擲一次", style=discord.ButtonStyle.primary)
    async def flip_again(self, interaction: discord.Interaction, button: ui.Button):
        result = random.choice(["正面", "反面"])
        embed = discord.Embed(title="擲硬幣", color=discord.Color.blue())
        embed.add_field(name="結果", value=result, inline=False)

        await interaction.response.edit_message(embed=embed, view=CoinFlipView())


class RouletteView(ui.View):
    def __init__(self, user_id: int, global_embed_config: dict):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.global_embed_config = global_embed_config
        self.chamber_position = 0
        self.bullet_position = random.randint(0, 5)
        self.attempts = 0

    def _create_embed(self, title: str, color: discord.Color) -> discord.Embed:
        embed = discord.Embed(title=title, color=color)

        global_author = self.global_embed_config.get("author", {})
        if global_author.get("name"):
            embed.set_author(
                name=global_author.get("name"),
                icon_url=global_author.get("icon_url"),
                url=global_author.get("url"),
            )

        return embed

    @ui.button(label="扣下扳機", style=discord.ButtonStyle.danger)
    async def pull_trigger(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("這不是你的遊戲", ephemeral=True)
            return

        self.chamber_position += 1

        if self.chamber_position - 1 == self.bullet_position:
            embed = self._create_embed("俄羅斯輪盤", discord.Color.red())
            embed.set_thumbnail(url=interaction.user.display_avatar.url)

            embed.add_field(
                name="**結果**",
                value=f"> {interaction.user.display_name} 中彈身亡",
                inline=False
            )
            embed.add_field(name="**回合數**", value=f"> {self.chamber_position}/6", inline=True)

            button.disabled = True
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
        else:
            if self.chamber_position >= 6:
                embed = self._create_embed("俄羅斯輪盤", discord.Color.gold())
                embed.set_thumbnail(url=interaction.user.display_avatar.url)

                embed.add_field(
                    name="**結果**",
                    value=f"> {interaction.user.display_name} 存活到最後",
                    inline=False
                )
                embed.add_field(name="**回合數**", value=f"> {self.chamber_position}/6", inline=True)

                button.disabled = True
                self.stop()
            else:
                embed = self._create_embed("俄羅斯輪盤", discord.Color.green())
                embed.set_thumbnail(url=interaction.user.display_avatar.url)

                embed.add_field(
                    name="**結果**",
                    value=f"> {interaction.user.display_name} 倖存",
                    inline=False
                )
                embed.add_field(name="**回合數**", value=f"> {self.chamber_position}/6", inline=True)

            await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class Games(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._load_data()

    def _load_data(self):
        with open(DATA_DIR / "games.json", "r", encoding="utf-8") as f:
            self.games_data = json.load(f)
        with open(DATA_DIR / "embed.json", "r", encoding="utf-8") as f:
            self.global_embed_config = json.load(f)
        with open(DATA_DIR / "8ball_responses.json", "r", encoding="utf-8") as f:
            self.eightball_data = json.load(f)

    @app_commands.command(name="roll", description="擲骰子")
    @app_commands.describe(sides="骰子面數")
    async def roll(self, interaction: discord.Interaction, sides: int = 6):
        if sides < 2:
            await interaction.response.send_message("骰子至少要有 2 面", ephemeral=True)
            return

        result = random.randint(1, sides)
        await interaction.response.send_message(f"擲出了 {result} 點（D{sides}）")

    @app_commands.command(name="choose", description="隨機選擇")
    @app_commands.describe(options="選項（用空格分隔）")
    async def choose(self, interaction: discord.Interaction, options: str):
        choices = options.split()
        if len(choices) < 2:
            await interaction.response.send_message("請提供至少 2 個選項", ephemeral=True)
            return

        result = random.choice(choices)
        await interaction.response.send_message(f"我選擇: {result}")

    @app_commands.command(name="8ball", description="神奇8號球")
    async def eight_ball(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EightBallModal(self.eightball_data["responses"]))

    @app_commands.command(name="coinflip", description="擲硬幣")
    async def coinflip(self, interaction: discord.Interaction):
        result = random.choice(["正面", "反面"])
        embed = discord.Embed(title="擲硬幣", color=discord.Color.blue())
        embed.add_field(name="結果", value=result, inline=False)

        await interaction.response.send_message(embed=embed, view=CoinFlipView())

    @app_commands.command(name="rps", description="猜拳遊戲")
    async def rock_paper_scissors(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="猜拳遊戲",
            description="點擊下方按鈕選擇你的出拳",
            color=discord.Color.blue(),
        )

        await interaction.response.send_message(embed=embed, view=RPSView())

    @app_commands.command(name="roulette", description="俄羅斯輪盤")
    async def roulette(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="俄羅斯輪盤",
            color=discord.Color.orange(),
        )

        global_author = self.global_embed_config.get("author", {})
        if global_author.get("name"):
            embed.set_author(
                name=global_author.get("name"),
                icon_url=global_author.get("icon_url"),
                url=global_author.get("url"),
            )

        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        embed.add_field(
            name="**遊戲規則**",
            value="> 彈匣中有 6 個位置，其中 1 發子彈",
            inline=False
        )
        embed.add_field(name="**回合數**", value="> 1/6", inline=True)

        await interaction.response.send_message(
            embed=embed, view=RouletteView(interaction.user.id, self.global_embed_config)
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))
