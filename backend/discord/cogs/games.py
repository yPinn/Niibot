"""Interactive game commands"""

import random

import discord
from discord import app_commands, ui
from discord.ext import commands

from core import DATA_DIR, EmbedFactory, UserBoundView, load_json


class RPSView(UserBoundView):
    def __init__(self, user_id: int, embed_factory: EmbedFactory) -> None:
        super().__init__(user_id, timeout=60)
        self._embed = embed_factory

    @ui.button(label="石頭", style=discord.ButtonStyle.secondary)
    async def rock(self, interaction: discord.Interaction, button: ui.Button["RPSView"]) -> None:
        await self.play_rps(interaction, "石頭")

    @ui.button(label="剪刀", style=discord.ButtonStyle.secondary)
    async def scissors(
        self, interaction: discord.Interaction, button: ui.Button["RPSView"]
    ) -> None:
        await self.play_rps(interaction, "剪刀")

    @ui.button(label="布", style=discord.ButtonStyle.secondary)
    async def paper(self, interaction: discord.Interaction, button: ui.Button["RPSView"]) -> None:
        await self.play_rps(interaction, "布")

    async def play_rps(self, interaction: discord.Interaction, choice: str) -> None:
        bot_choice = random.choice(["石頭", "剪刀", "布"])

        if choice == bot_choice:
            result, color = "平手", discord.Color.gold()
        elif (
            (choice == "石頭" and bot_choice == "剪刀")
            or (choice == "剪刀" and bot_choice == "布")
            or (choice == "布" and bot_choice == "石頭")
        ):
            result, color = "你贏了", discord.Color.green()
        else:
            result, color = "你輸了", discord.Color.red()

        embed = self._embed.build(title="猜拳遊戲", color=color)
        embed.add_field(name="你的選擇", value=choice, inline=True)
        embed.add_field(name="Bot 的選擇", value=bot_choice, inline=True)
        embed.add_field(name="結果", value=result, inline=False)

        await interaction.response.edit_message(
            embed=embed, view=RPSView(self.user_id, self._embed)
        )


class RouletteView(ui.View):
    def __init__(self, user_id: int, embed_factory: EmbedFactory):
        super().__init__(timeout=300)
        self.user_id = user_id
        self._embed = embed_factory
        self.chamber_position = 0
        self.bullet_position = random.randint(0, 5)
        self.attempts = 0
        self.message: discord.Message | None = None

    def _build_result_embed(
        self,
        interaction: discord.Interaction,
        color: discord.Color,
        result_text: str,
    ) -> discord.Embed:
        embed: discord.Embed = self._embed.build(title="俄羅斯輪盤", color=color)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="**結果**", value=f"> {result_text}", inline=False)
        embed.add_field(name="**回合數**", value=f"> {self.chamber_position}/6", inline=True)
        return embed

    @ui.button(label="扣下扳機", style=discord.ButtonStyle.danger)
    async def pull_trigger(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("這不是你的遊戲", ephemeral=True)
            return

        self.chamber_position += 1

        if self.chamber_position - 1 == self.bullet_position:
            embed = self._build_result_embed(
                interaction, discord.Color.red(), f"{interaction.user.display_name} 中彈身亡"
            )
            button.disabled = True
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
        else:
            if self.chamber_position >= 6:
                embed = self._build_result_embed(
                    interaction, discord.Color.gold(), f"{interaction.user.display_name} 存活到最後"
                )
                button.disabled = True
                self.stop()
            else:
                embed = self._build_result_embed(
                    interaction, discord.Color.green(), f"{interaction.user.display_name} 倖存"
                )
            await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.HTTPException):
                pass


class GamesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._load_data()

    def _load_data(self) -> None:
        self.games_data = load_json(DATA_DIR / "games.json")
        self._embed = EmbedFactory(load_json(DATA_DIR / "embed.json"))

    game = app_commands.Group(name="game", description="遊戲指令")

    @game.command(name="roll", description="擲骰子")
    @app_commands.describe(sides="骰子面數（預設 6）")
    async def game_roll(self, interaction: discord.Interaction, sides: int = 6) -> None:
        if sides < 2:
            await interaction.response.send_message("骰子至少要有 2 面", ephemeral=True)
            return

        result = random.randint(1, sides)
        await interaction.response.send_message(f"擲出了 {result} 點（D{sides}）")

    @game.command(name="choose", description="隨機選擇")
    @app_commands.describe(options="選項（用空格分隔）")
    async def game_choose(self, interaction: discord.Interaction, options: str) -> None:
        choices = options.split()
        if len(choices) < 2:
            await interaction.response.send_message("請提供至少 2 個選項", ephemeral=True)
            return

        result = random.choice(choices)
        await interaction.response.send_message(f"我選擇: {result}")

    @game.command(name="rps", description="猜拳遊戲")
    async def game_rps(self, interaction: discord.Interaction) -> None:
        embed = self._embed.build(
            title="猜拳遊戲",
            description="點擊下方按鈕選擇你的出拳",
            color=discord.Color.blue(),
        )

        await interaction.response.send_message(
            embed=embed, view=RPSView(interaction.user.id, self._embed)
        )

    @game.command(name="roulette", description="俄羅斯輪盤")
    async def game_roulette(self, interaction: discord.Interaction) -> None:
        embed = self._embed.build(title="俄羅斯輪盤", color=discord.Color.orange())
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(
            name="**遊戲規則**", value="> 彈匣中有 6 個位置，其中 1 發子彈", inline=False
        )
        embed.add_field(name="**回合數**", value="> 1/6", inline=True)

        view = RouletteView(interaction.user.id, self._embed)
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GamesCog(bot))
