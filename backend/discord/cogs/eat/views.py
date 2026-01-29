"""Eat feature UI views."""

from typing import TYPE_CHECKING, Union

import discord
from discord import ui

if TYPE_CHECKING:
    from .cog import EatCog


class CategoryButton(ui.Button["CategoryButtonsView"]):
    """分類選擇按鈕"""

    def __init__(self, cog: "EatCog", category: str, user: Union[discord.User, discord.Member]):
        super().__init__(
            label=category,
            style=discord.ButtonStyle.primary,
            custom_id=f"cat_{category}"
        )
        self.cog = cog
        self.category = category
        self.user = user

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("這不是你的選單", ephemeral=True)
            return

        choice = await self.cog.get_recommendation(self.category, str(interaction.user.id))
        if not choice:
            await interaction.response.send_message(
                f"找不到「{self.category}」的資料或該分類為空", ephemeral=True
            )
            return

        embed = self.cog.create_embed(
            title=f"{self.category} 推薦",
            description=f"**{choice}**"
        )
        view = RecommendationView(self.cog, self.category, self.user)
        await interaction.response.edit_message(embed=embed, view=view)


class CategoryButtonsView(ui.View):
    """分類選擇按鈕視圖"""

    def __init__(self, cog: "EatCog", user: Union[discord.User, discord.Member]):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user
        self._add_category_buttons()

    def _add_category_buttons(self) -> None:
        categories = list(self.cog.data.get("categories", {}).keys())[:25]
        for category in categories:
            self.add_item(CategoryButton(self.cog, category, self.user))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("這不是你的選單", ephemeral=True)
            return False
        return True


class RecommendationView(ui.View):
    """推薦結果視圖（換一個、返回）"""

    def __init__(self, cog: "EatCog", category: str, user: Union[discord.User, discord.Member]):
        super().__init__(timeout=300)
        self.cog = cog
        self.category = category
        self.user = user

    @ui.button(label="換一個", style=discord.ButtonStyle.success)
    async def reload_button(self, interaction: discord.Interaction, button: ui.Button["RecommendationView"]) -> None:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("這不是你的選單", ephemeral=True)
            return

        choice = await self.cog.get_recommendation(self.category, str(interaction.user.id))
        if not choice:
            await interaction.response.send_message(f"找不到「{self.category}」的資料", ephemeral=True)
            return

        embed = self.cog.create_embed(
            title=f"{self.category} 推薦",
            description=f"**{choice}**"
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="回分類列表", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: ui.Button["RecommendationView"]) -> None:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("這不是你的選單", ephemeral=True)
            return

        time_category = self.cog.get_time_based_category()
        description = "點選下方按鈕以獲得該分類的推薦餐點"
        if time_category and time_category in self.cog.data["categories"]:
            description += f"\n\n> **目前時段推薦：{time_category}**"

        embed = self.cog.create_embed(title="請選擇餐點分類", description=description)
        await interaction.response.edit_message(embed=embed, view=CategoryButtonsView(self.cog, self.user))
