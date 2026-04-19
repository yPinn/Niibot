"""Eat feature UI views."""

from typing import TYPE_CHECKING

import discord
from discord import ui

if TYPE_CHECKING:
    from .cog import EatCog

ITEMS_PER_PAGE = 10


class CategoryButton(ui.Button["CategoryButtonsView"]):
    """分類選擇按鈕"""

    def __init__(
        self,
        cog: "EatCog",
        category: str,
        user: discord.User | discord.Member,
        is_recommended: bool = False,
    ):
        style = discord.ButtonStyle.success if is_recommended else discord.ButtonStyle.secondary
        super().__init__(label=category, style=style, custom_id=f"cat_{category}")
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
                f"「{self.category}」目前沒有項目", ephemeral=True
            )
            return

        item_count = self.cog.get_category_item_count(self.category)
        embed = self.cog.create_embed(
            title=f"{self.category} 推薦",
            description=f"**{choice}**",
            footer=f"{item_count} 項可選",
        )
        view = RecommendationView(self.cog, self.category, self.user)
        await interaction.response.edit_message(embed=embed, view=view)


class CategoryButtonsView(ui.View):
    """分類選擇按鈕視圖"""

    def __init__(
        self, cog: "EatCog", user: discord.User | discord.Member, time_category: str | None = None
    ):
        super().__init__(timeout=180)
        self.cog = cog
        self.user = user
        self.time_category = time_category
        self._add_category_buttons()

    def _add_category_buttons(self) -> None:
        categories = list(self.cog.data.get("categories", {}).keys())
        # 依名稱長度排序，較短的在前
        categories.sort(key=len)

        # 時段推薦分類排在最前面
        if self.time_category and self.time_category in categories:
            categories.remove(self.time_category)
            categories.insert(0, self.time_category)

        for category in categories[:25]:
            is_recommended = category == self.time_category
            self.add_item(CategoryButton(self.cog, category, self.user, is_recommended))

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("這不是你的選單", ephemeral=True)
            return False
        return True


class RecommendationView(ui.View):
    """推薦結果視圖"""

    def __init__(self, cog: "EatCog", category: str, user: discord.User | discord.Member):
        super().__init__(timeout=180)
        self.cog = cog
        self.category = category
        self.user = user

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True

    @ui.button(label="換一個", style=discord.ButtonStyle.primary)
    async def reload_button(
        self, interaction: discord.Interaction, button: ui.Button["RecommendationView"]
    ) -> None:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("這不是你的選單", ephemeral=True)
            return

        choice = await self.cog.get_recommendation(self.category, str(interaction.user.id))
        if not choice:
            await interaction.response.send_message(
                f"「{self.category}」目前沒有項目", ephemeral=True
            )
            return

        item_count = self.cog.get_category_item_count(self.category)
        embed = self.cog.create_embed(
            title=f"{self.category} 推薦",
            description=f"**{choice}**",
            footer=f"{item_count} 項可選",
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="返回", style=discord.ButtonStyle.secondary)
    async def back_button(
        self, interaction: discord.Interaction, button: ui.Button["RecommendationView"]
    ) -> None:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("這不是你的選單", ephemeral=True)
            return

        time_category = self.cog.get_time_based_category()
        total = len(self.cog.data["categories"])
        desc = "點選分類獲得推薦"
        if time_category:
            desc += f"\n時段推薦：**{time_category}**"

        embed = self.cog.create_embed(
            title="今天吃什麼", description=desc, footer=f"{total} 個分類"
        )
        view = CategoryButtonsView(self.cog, self.user, time_category)
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="確定", style=discord.ButtonStyle.success)
    async def confirm_button(
        self, interaction: discord.Interaction, button: ui.Button["RecommendationView"]
    ) -> None:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("這不是你的選單", ephemeral=True)
            return

        # 停用所有按鈕，保留結果
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True

        await interaction.response.edit_message(view=self)


class ItemListView(ui.View):
    """項目列表分頁視圖"""

    def __init__(self, cog: "EatCog", category: str, items: list[str], page: int = 0):
        super().__init__(timeout=120)
        self.cog = cog
        self.category = category
        self.items = items
        self.page = page
        self.max_page = (len(items) - 1) // ITEMS_PER_PAGE
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page >= self.max_page

    def get_embed(self) -> discord.Embed:
        start = self.page * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        page_items = self.items[start:end]
        desc = "\n".join(f"{start + i + 1}. {item}" for i, item in enumerate(page_items))
        return self.cog.create_embed(
            title=f"{self.category} 清單",
            description=desc,
            footer=f"{self.page + 1}/{self.max_page + 1} 頁 | 共 {len(self.items)} 項",
        )

    @ui.button(label="<", style=discord.ButtonStyle.secondary)
    async def prev_btn(
        self, interaction: discord.Interaction, button: ui.Button["ItemListView"]
    ) -> None:
        self.page = max(0, self.page - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @ui.button(label=">", style=discord.ButtonStyle.secondary)
    async def next_btn(
        self, interaction: discord.Interaction, button: ui.Button["ItemListView"]
    ) -> None:
        self.page = min(self.max_page, self.page + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
