import asyncio
import os
import random

import discord
from discord import app_commands
from discord.ext import commands

from utils import util
from utils.config_manager import config
from utils.logger import BotLogger
from ui.components import BaseView, EmbedBuilder, ErrorHandler


# Eat 模組專用的 Embed 輔助類
class EatEmbeds:
    """Eat 模組專用的 Embed 建立器"""
    
    @staticmethod
    def category_selection():
        """分類選擇的 Embed"""
        return EmbedBuilder.selection_prompt(
            title="🍽️ 請選擇餐點分類",
            description="點選下方按鈕以獲得該分類的推薦餐點。"
        )
    
    @staticmethod
    def dish_recommendation(category: str, choice: str):
        """餐點推薦的 Embed"""
        return discord.Embed(
            title=f"🍽️ {category} 推薦餐點",
            description=f"**{choice}**",
            color=EmbedBuilder.Colors.PRIMARY
        )
    
    @staticmethod
    def categories_list(categories: list[str]):
        """分類列表的 Embed"""
        return EmbedBuilder.list_display(
            title="📋 可用分類清單",
            items=[f"{cat}" for cat in categories],
            color=EmbedBuilder.Colors.INFO
        )
    
    @staticmethod
    def menu_display(category: str, items: list[str]):
        """選單顯示的 Embed"""
        return EmbedBuilder.list_display(
            title=f"🍽️ {category} 的餐點選項",
            items=[f"{opt}" for opt in sorted(items)],
            color=EmbedBuilder.Colors.WARNING
        )
    
    @staticmethod
    def categories_info(data: dict):
        """分類資訊的 Embed"""
        categories_info = []
        for category_key, items in data.items():
            categories_info.append(f"**{category_key}** ({len(items)} 項)")
        
        return EmbedBuilder.list_display(
            title="🗂️ 所有餐點分類",
            items=categories_info,
            color=EmbedBuilder.Colors.SUCCESS
        )


class CategoryButtonsView(BaseView):
    def __init__(self, data: dict, user: discord.User):
        super().__init__(user)
        self.data = data
        # 一次最多顯示25個按鈕
        for category in sorted(data.keys())[:25]:
            button = CategoryButton(category)
            self.add_item(button)


class CategoryButton(discord.ui.Button):
    def __init__(self, category: str):
        super().__init__(label=category, style=discord.ButtonStyle.primary)
        self.category = category

    async def callback(self, interaction: discord.Interaction):
        options = self.view.data.get(self.category, [])
        if not options:
            await interaction.response.send_message(
                f"❌ 「{self.category}」分類沒有餐點", ephemeral=True
            )
            return

        choice = random.choice(options)
        embed = EatEmbeds.dish_recommendation(self.category, choice)
        view = DishButtonsView(self.category, options, interaction.user)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()


class DishButtonsView(BaseView):
    def __init__(self, category: str, options: list[str], user: discord.User):
        super().__init__(user)
        self.category = category
        self.options = options

        reload_btn = ReloadButton(category, options)
        back_btn = BackButton()
        self.add_item(reload_btn)
        self.add_item(back_btn)


class ReloadButton(discord.ui.Button):
    def __init__(self, category: str, options: list[str]):
        super().__init__(label="換一個", style=discord.ButtonStyle.success)
        self.category = category
        self.options = options

    async def callback(self, interaction: discord.Interaction):
        choice = random.choice(self.options)
        embed = EatEmbeds.dish_recommendation(self.category, choice)
        view = DishButtonsView(self.category, self.options, interaction.user)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()


class BackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="回分類列表", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Eat")
        if not cog:
            await interaction.response.send_message("系統錯誤", ephemeral=True)
            return

        embed = EatEmbeds.category_selection()
        view = CategoryButtonsView(cog.data, interaction.user)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()


class Eat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_file = "eat.json"
        self.data = {}
        self._lock = asyncio.Lock()
        BotLogger.info("Eat", "Eat cog 初始化完成")

    async def initialize(self):
        """初始化資料"""
        try:
            self.data = await util.read_json(util.get_data_file_path(self.data_file))
            if not isinstance(self.data, dict):
                self.data = {}
            category_count = len(self.data)
            item_count = sum(len(items) for items in self.data.values())
            BotLogger.info(
                "Eat", f"載入了 {category_count} 個分類，共 {item_count} 個項目")
        except Exception as e:
            BotLogger.error("Eat", "初始化資料失敗", e)
            self.data = {}

    async def load_data(self):
        """重新載入資料"""
        try:
            self.data = await util.read_json(util.get_data_file_path(self.data_file))
            if not isinstance(self.data, dict):
                self.data = {}
        except Exception as e:
            BotLogger.error("Eat", "載入資料失敗", e)
            self.data = {}

    async def save_data(self):
        """儲存資料"""
        try:
            success = await util.write_json(util.get_data_file_path(self.data_file), self.data)
            if not success:
                BotLogger.error("Eat", "儲存資料失敗")
        except Exception as e:
            BotLogger.error("Eat", "儲存資料異常", e)

    def _normalize_category(self, category: str) -> str:
        """規範化分類名稱"""
        return util.normalize_text(category)

    def _category_exists(self, category: str) -> bool:
        """檢查分類是否存在且不為空"""
        category_key = self._normalize_category(category)
        return category_key in self.data and self.data[category_key]

    def _get_category_items(self, category: str) -> list[str]:
        """獲取分類中的項目"""
        category_key = self._normalize_category(category)
        return self.data.get(category_key, [])

    async def _show_category_selection(
        self, user: discord.User, ctx_or_interaction, is_slash: bool = False
    ):
        """顯示分類選擇介面 - 統一處理文字和斜線指令"""
        if not self.data:
            message = "📭 目前沒有任何分類，請先新增一些內容。"
            if is_slash:
                await ctx_or_interaction.response.send_message(message, ephemeral=True)
            else:
                await ctx_or_interaction.send(message)
            return

        embed = EatEmbeds.category_selection()
        view = CategoryButtonsView(self.data, user)

        if is_slash:
            await ctx_or_interaction.response.send_message(embed=embed, view=view)
            view.message = await ctx_or_interaction.original_response()
        else:
            response_message = await ctx_or_interaction.send(
                embed=embed, view=view, reference=ctx_or_interaction.message, mention_author=False
            )
            view.message = response_message

    async def _show_dish_recommendation(
        self, user: discord.User, category: str, ctx_or_interaction, is_slash: bool = False
    ):
        """顯示餐點推薦 - 統一處理文字和斜線指令"""
        if not self._category_exists(category):
            message = f"❌ 找不到「{category}」的資料或該分類為空。"
            if is_slash:
                await ctx_or_interaction.response.send_message(message, ephemeral=True)
            else:
                await ctx_or_interaction.send(message)
            return

        items = self._get_category_items(category)
        choice = random.choice(items)
        message = f"🍽️ 推薦你點：**{choice}**"

        if is_slash:
            await ctx_or_interaction.response.send_message(message)
        else:
            await ctx_or_interaction.send(message)

    async def _handle_eat_command(
        self, user: discord.User, category: str, ctx_or_interaction, is_slash: bool = False
    ):
        """處理 eat 指令邏輯 - 統一處理文字和斜線指令"""
        try:
            if category is None:
                await self._show_category_selection(user, ctx_or_interaction, is_slash)
            else:
                await self._show_dish_recommendation(user, category, ctx_or_interaction, is_slash)
        except Exception as e:
            BotLogger.error("Eat", f"處理eat指令時發生錯誤: {e}")
            message = "❌ 系統發生錯誤，請稍後再試。"
            if is_slash:
                if ctx_or_interaction.response.is_done():
                    await ctx_or_interaction.followup.send(message, ephemeral=True)
                else:
                    await ctx_or_interaction.response.send_message(message, ephemeral=True)
            else:
                await ctx_or_interaction.send(message)

    @commands.Cog.listener()
    async def on_ready(self):
        await self.initialize()

    # 文字指令
    @commands.command(aliases=["點"], help="幫你想要吃什麼，使用方法：!eat 類別 或 !eat")
    async def eat(self, ctx: commands.Context, *, category: str = None):
        await self._handle_eat_command(ctx.author, category, ctx, is_slash=False)

    @commands.command(name="cat", help="顯示所有分類")
    async def eat_list(self, ctx: commands.Context):
        if not self.data:
            await ctx.send("📭 目前沒有任何分類，請先新增一些內容。")
            return

        categories = sorted(self.data.keys())
        embed = EatEmbeds.categories_list(categories)
        await ctx.send(embed=embed)

    @commands.command(name="additem", help="新增餐點選項到分類，例如：!additem 主餐 蛋餅")
    async def add_eat(self, ctx, category: str, *, item: str):
        await self._add_item_to_category(ctx, category, item, is_slash=False)

    @commands.command(name="delitem", help="從分類中移除選項，例如：!delitem 主餐 蛋餅")
    async def remove_eat(self, ctx, category: str, *, item: str):
        await self._remove_item_from_category(ctx, category, item, is_slash=False)

    @commands.command(name="menu", help="顯示某分類的所有選項，例如：!menu 主餐")
    async def show_eat(self, ctx, *, category: str):
        await self._show_category_menu(ctx, category, is_slash=False)

    @commands.command(name="delcat", help="刪除整個分類，例如：!delcat 早餐")
    async def delete_category(self, ctx, *, category: str):
        await self._delete_category(ctx, category, is_slash=False)

    # 斜線指令
    @app_commands.command(name="eat", description="獲得餐點推薦")
    @app_commands.describe(category="餐點分類 (可選，不填會顯示分類選擇按鈕)")
    async def slash_eat(self, interaction: discord.Interaction, category: str = None):
        async with self._lock:
            await self.load_data()
        await self._handle_eat_command(interaction.user, category, interaction, is_slash=True)

    @app_commands.command(name="menu", description="查看指定分類的所有餐點選項")
    @app_commands.describe(category="要查看的餐點分類")
    async def slash_menu(self, interaction: discord.Interaction, category: str):
        await self._show_category_menu(interaction, category, is_slash=True)

    @app_commands.command(name="categories", description="查看所有可用的餐點分類")
    async def slash_categories(self, interaction: discord.Interaction):
        async with self._lock:
            await self.load_data()
            if self.data:
                embed = EatEmbeds.categories_info(self.data)
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(
                    "📭 目前沒有任何分類，請先新增一些內容。", ephemeral=True
                )

    @app_commands.command(name="add_food", description="新增餐點到指定分類")
    @app_commands.describe(category="餐點分類", item="要新增的餐點名稱")
    async def slash_add_food(self, interaction: discord.Interaction, category: str, item: str):
        await self._add_item_to_category(interaction, category, item, is_slash=True)

    @app_commands.command(name="remove_food", description="從指定分類移除餐點")
    @app_commands.describe(category="餐點分類", item="要移除的餐點名稱")
    async def slash_remove_food(self, interaction: discord.Interaction, category: str, item: str):
        await self._remove_item_from_category(interaction, category, item, is_slash=True)

    @app_commands.command(name="delete_category", description="刪除整個餐點分類")
    @app_commands.describe(category="要刪除的餐點分類")
    async def slash_delete_category(self, interaction: discord.Interaction, category: str):
        await self._delete_category(interaction, category, is_slash=True)

    # 統一的核心業務邏輯方法
    async def _add_item_to_category(
        self, ctx_or_interaction, category: str, item: str, is_slash: bool
    ):
        """新增項目到分類"""
        category_key = self._normalize_category(category)
        item_key = util.normalize_text(item)

        async with self._lock:
            await self.load_data()
            self.data.setdefault(category_key, [])

            normalized_items = [util.normalize_text(
                x) for x in self.data[category_key]]
            if item_key in normalized_items:
                message = f"⚠️ 「{item}」已經在「{category}」分類中了。"
                ephemeral = True
            else:
                self.data[category_key].append(item)
                await self.save_data()
                message = f"✅ 已將「{item}」新增到「{category}」分類。"
                ephemeral = False

            if is_slash:
                await ctx_or_interaction.response.send_message(message, ephemeral=ephemeral)
            else:
                await ctx_or_interaction.send(message)

    async def _remove_item_from_category(
        self, ctx_or_interaction, category: str, item: str, is_slash: bool
    ):
        """從分類中移除項目"""
        category_key = self._normalize_category(category)
        item_key = util.normalize_text(item)

        async with self._lock:
            await self.load_data()

            if category_key in self.data:
                for idx, existing_item in enumerate(self.data[category_key]):
                    if util.normalize_text(existing_item) == item_key:
                        removed = self.data[category_key].pop(idx)
                        if not self.data[category_key]:  # 如果分類變空，刪除分類
                            del self.data[category_key]
                        await self.save_data()
                        message = f"🗑️ 已從「{category}」分類中移除「{removed}」。"
                        ephemeral = False
                        break
                else:
                    message = f"❌ 在「{category}」分類中找不到「{item}」。"
                    ephemeral = True
            else:
                message = f"❌ 找不到「{category}」分類。"
                ephemeral = True

            if is_slash:
                await ctx_or_interaction.response.send_message(message, ephemeral=ephemeral)
            else:
                await ctx_or_interaction.send(message)

    async def _show_category_menu(self, ctx_or_interaction, category: str, is_slash: bool):
        """顯示分類選單"""
        if is_slash:
            async with self._lock:
                await self.load_data()

        if not self._category_exists(category):
            message = f"❌ 沒有找到「{category}」分類或該分類為空。"
            if is_slash:
                await ctx_or_interaction.response.send_message(message, ephemeral=True)
            else:
                await ctx_or_interaction.send(message)
            return

        items = self._get_category_items(category)
        embed = EatEmbeds.menu_display(category, items)

        if is_slash:
            await ctx_or_interaction.response.send_message(embed=embed)
        else:
            await ctx_or_interaction.send(embed=embed)

    async def _delete_category(self, ctx_or_interaction, category: str, is_slash: bool):
        """刪除分類"""
        category_key = self._normalize_category(category)

        async with self._lock:
            await self.load_data()

            if category_key in self.data:
                del self.data[category_key]
                await self.save_data()
                message = f"🗑️ 已刪除分類「{category}」。"
                ephemeral = False
            else:
                message = f"❌ 沒有找到「{category}」分類。"
                ephemeral = True

            if is_slash:
                await ctx_or_interaction.response.send_message(message, ephemeral=ephemeral)
            else:
                await ctx_or_interaction.send(message)

    # 錯誤處理 - 使用統一的錯誤處理類
    @add_eat.error
    async def add_eat_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ErrorHandler.handle_missing_argument(ctx, "additem", "主餐 蛋餅")
        else:
            ErrorHandler.log_command_error("additem", error)

    @remove_eat.error
    async def remove_eat_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ErrorHandler.handle_missing_argument(ctx, "delitem", "主餐 蛋餅")
        else:
            ErrorHandler.log_command_error("delitem", error)

    @show_eat.error
    async def show_eat_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ErrorHandler.handle_missing_argument(ctx, "menu", "主餐")
        else:
            ErrorHandler.log_command_error("menu", error)

    @delete_category.error
    async def delete_category_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ErrorHandler.handle_missing_argument(ctx, "delcat", "早餐")
        else:
            ErrorHandler.log_command_error("delcat", error)

    # 自動完成功能 - 統一的自動完成邏輯
    async def _category_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """分類自動完成"""
        async with self._lock:
            await self.load_data()
            choices = []
            current_lower = current.lower()

            for category_key in self.data.keys():
                if current_lower in category_key.lower():
                    if len(choices) < 25:
                        choices.append(app_commands.Choice(
                            name=category_key, value=category_key))
                    else:
                        break
            return choices

    async def _food_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """食物項目自動完成"""
        # 獲取當前已輸入的分類
        category = (
            interaction.namespace.category if hasattr(
                interaction.namespace, 'category') else None
        )
        if not category:
            return []

        async with self._lock:
            await self.load_data()
            category_key = self._normalize_category(category)

            if category_key not in self.data:
                return []

            choices = []
            current_lower = current.lower()

            for item in self.data[category_key]:
                if current_lower in item.lower():
                    if len(choices) < 25:
                        choices.append(app_commands.Choice(
                            name=item, value=item))
                    else:
                        break
            return choices

    # 為相關指令添加自動完成
    def setup_autocomplete(self):
        """設置自動完成功能"""
        self.slash_eat.autocomplete('category')(self._category_autocomplete)
        self.slash_menu.autocomplete('category')(self._category_autocomplete)
        self.slash_add_food.autocomplete(
            'category')(self._category_autocomplete)
        self.slash_remove_food.autocomplete(
            'category')(self._category_autocomplete)
        self.slash_remove_food.autocomplete('item')(self._food_autocomplete)
        self.slash_delete_category.autocomplete(
            'category')(self._category_autocomplete)


async def setup(bot: commands.Bot):
    eat_cog = Eat(bot)
    await eat_cog.initialize()  # 確保資料初始化完成
    eat_cog.setup_autocomplete()  # 設置自動完成
    await bot.add_cog(eat_cog)
