import asyncio
import os
import random

import discord
from discord import app_commands
from discord.ext import commands

from utils import util
from utils.logger import BotLogger
from utils.config_manager import config


# 簡化的 UI 類別
class CategoryButtonsView(discord.ui.View):
    def __init__(self, data: dict, user: discord.User, message: discord.Message = None):
        super().__init__(timeout=60)
        self.data = data
        self.user = user
        self.message = message
        # 一次最多顯示25個按鈕
        for category in sorted(data.keys())[:25]:
            button = CategoryButton(category)
            self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 只能由原始使用者操作", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        """逾時時顯示簡單的逾時訊息"""
        if self.message:
            try:
                embed = discord.Embed(
                    title="⏰ 操作已逾時",
                    description="請重新使用 ?eat 指令",
                    color=discord.Color.light_grey()
                )
                await self.message.edit(embed=embed, view=None)
            except (discord.NotFound, discord.HTTPException):
                pass  # 訊息已被刪除或其他錯誤，忽略


class CategoryButton(discord.ui.Button):
    def __init__(self, category: str):
        super().__init__(label=category, style=discord.ButtonStyle.primary)
        self.category = category

    async def callback(self, interaction: discord.Interaction):
        options = self.view.data.get(self.category, [])
        if not options:
            await interaction.response.send_message(f"❌ 「{self.category}」分類沒有餐點", ephemeral=True)
            return

        choice = random.choice(options)
        embed = discord.Embed(
            title=f"🍽️ {self.category} 推薦餐點",
            description=f"**{choice}**",
            color=discord.Color.blurple()
        )
        # 創建 view 並一次性編輯訊息
        view = DishButtonsView(self.category, options, interaction.user)
        await interaction.response.edit_message(embed=embed, view=view)
        # 設置訊息引用到 view
        view.message = await interaction.original_response()


class DishButtonsView(discord.ui.View):
    def __init__(self, category: str, options: list[str], user: discord.User, message: discord.Message = None):
        super().__init__(timeout=60)
        self.category = category
        self.options = options
        self.user = user
        self.message = message

        reload_btn = ReloadButton(category, options)
        back_btn = BackButton()
        self.add_item(reload_btn)
        self.add_item(back_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ 只能由原始使用者操作", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        """逾時時將所有按鈕變灰並禁用"""
        if self.message:
            try:
                embed = discord.Embed(
                    title="⏰ 操作已逾時",
                    description="請重新使用 ?eat 指令",
                    color=discord.Color.light_grey()
                )
                await self.message.edit(embed=embed, view=None)
            except (discord.NotFound, discord.HTTPException):
                pass  # 訊息已被刪除或其他錯誤，忽略


class ReloadButton(discord.ui.Button):
    def __init__(self, category: str, options: list[str]):
        super().__init__(label="換一個", style=discord.ButtonStyle.success)
        self.category = category
        self.options = options

    async def callback(self, interaction: discord.Interaction):
        choice = random.choice(self.options)
        embed = discord.Embed(
            title=f"🍽️ {self.category} 推薦餐點",
            description=f"**{choice}**",
            color=discord.Color.blurple()
        )
        # 創建 view 並一次性編輯訊息
        view = DishButtonsView(self.category, self.options, interaction.user)
        await interaction.response.edit_message(embed=embed, view=view)
        # 設置訊息引用到 view
        view.message = await interaction.original_response()


class BackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="回分類列表", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Eat")
        if not cog:
            await interaction.response.send_message("系統錯誤", ephemeral=True)
            return

        embed = discord.Embed(
            title="🍽️ 請選擇餐點分類",
            description="點選下方按鈕以獲得該分類的推薦餐點。",
            color=discord.Color.green()
        )
        # 創建 view 並一次性編輯訊息
        view = CategoryButtonsView(cog.data, interaction.user)
        await interaction.response.edit_message(embed=embed, view=view)
        # 設置訊息引用到 view
        view.message = await interaction.original_response()


class Eat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_file = "eat.json"
        self.data = {}
        self._lock = asyncio.Lock()
        BotLogger.info("Eat", "Eat cog 初始化完成")

    async def initialize(self):
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

    async def save_data(self):
        try:
            success = await util.write_json(util.get_data_file_path(self.data_file), self.data)
            if not success:
                BotLogger.error("Eat", "儲存資料失敗")
        except Exception as e:
            BotLogger.error("Eat", "儲存資料異常", e)

    @commands.Cog.listener()
    async def on_ready(self):
        await self.initialize()

    async def _handle_eat_command(self, user: discord.User, category: str = None, ctx: commands.Context = None):
        """處理 eat 指令邏輯"""
        try:
            if category is None:
                await self._show_category_selection(user, ctx)
            else:
                await self._show_dish_recommendation(user, category, ctx)
        except Exception as e:
            BotLogger.error("Eat", f"處理eat指令時發生錯誤: {e}")
            await ctx.send("❌ 系統發生錯誤，請稍後再試。")

    async def _show_category_selection(self, user: discord.User, ctx: commands.Context):
        """顯示分類選擇界面"""
        if not self.data:
            await ctx.send("📭 目前沒有任何分類，請先新增一些內容。")
            return

        embed = discord.Embed(
            title="🍽️ 請選擇餐點分類",
            description="點選下方按鈕以獲得該分類的推薦餐點。",
            color=discord.Color.green()
        )
        
        response_message = await ctx.send(embed=embed, view=None, reference=ctx.message, mention_author=False)
        view = CategoryButtonsView(self.data, user, response_message)
        await response_message.edit(embed=embed, view=view)

    async def _show_dish_recommendation(self, user: discord.User, category: str, ctx: commands.Context):
        """顯示餐點推薦（簡單模式，無按鈕）"""
        category_key = util.normalize_text(category)
        if category_key not in self.data or not self.data[category_key]:
            await ctx.send(f"❌ 找不到「{category}」的資料或該分類為空。")
            return

        choice = random.choice(self.data[category_key])
        await ctx.send(f"🍽️ 推薦你點：**{choice}**")

    # 文字指令：!eat 類別
    @commands.command(aliases=["點"], help="幫你想要吃什麼，使用方法：!eat 類別 或 !eat")
    async def eat(self, ctx: commands.Context, *, category: str = None):
        await self._handle_eat_command(ctx.author, category, ctx)


    # 其他管理指令不動...

    @commands.command(name="cat", help="顯示所有分類")
    async def eat_list(self, ctx: commands.Context):
        if not self.data:
            await ctx.send("📭 目前沒有任何分類，請先新增一些內容。")
            return

        categories = sorted(self.data.keys())
        embed = discord.Embed(title="📋 可用分類列表", color=discord.Color.blue())
        embed.description = "\n".join(f"- {cat}" for cat in categories)

        await ctx.send(embed=embed)

    @commands.command(name="additem", help="新增餐點選項到分類，例如：!additem 主餐 蛋餅")
    async def add_eat(self, ctx, category: str, *, item: str):
        category_key = util.normalize_text(category)
        item_key = util.normalize_text(item)
        async with self._lock:
            self.data.setdefault(category_key, [])
            normalized_items = [util.normalize_text(
                x) for x in self.data[category_key]]
            if item_key in normalized_items:
                await ctx.send("⚠️ 該選項已存在。")
                return
            self.data[category_key].append(item)
            await self.save_data()
        await ctx.send(f"✅ 已將「{item}」新增到「{category}」中。")

    @add_eat.error
    async def add_eat_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ 請提供分類和餐點名稱，例如：`?additem 主餐 蛋餅`")
        else:
            BotLogger.error("Eat", f"additem 指令錯誤: {error}")

    @commands.command(name="delitem", help="從分類中移除選項，例如：!delitem 主餐 蛋餅")
    async def remove_eat(self, ctx, category: str, *, item: str):
        category_key = util.normalize_text(category)
        item_key = util.normalize_text(item)
        async with self._lock:
            if category_key in self.data:
                for idx, existing_item in enumerate(self.data[category_key]):
                    if util.normalize_text(existing_item) == item_key:
                        removed = self.data[category_key].pop(idx)
                        await self.save_data()
                        await ctx.send(f"🗑️ 已移除「{removed}」從「{category}」。")
                        return
            await ctx.send("⚠️ 找不到該分類或選項。")

    @remove_eat.error
    async def remove_eat_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ 請提供分類和餐點名稱，例如：`?delitem 主餐 蛋餅`")
        else:
            BotLogger.error("Eat", f"delitem 指令錯誤: {error}")

    @commands.command(name="menu", help="顯示某分類的所有選項，例如：!menu 主餐")
    async def show_eat(self, ctx, *, category: str):
        if not category:
            await ctx.send("❓ 要吃什麼？請輸入 `?menu 類別`，例如 `?menu 主餐`")
            return
        category_key = util.normalize_text(category)
        if category_key in self.data and self.data[category_key]:
            options = sorted(self.data[category_key])
            embed = discord.Embed(
                title=f"🍽️ {category} 的餐點選項", color=discord.Color.orange())
            embed.description = "\n".join(f"- {opt}" for opt in options)
            await ctx.send(embed=embed)
        else:
            await ctx.send("⚠️ 沒有找到資料或該分類為空。")

    @show_eat.error
    async def show_eat_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❓ 請輸入要查看的分類，例如：`?menu 主餐`")
        else:
            BotLogger.error("Eat", f"menu 指令錯誤: {error}")

    @commands.command(name="delcat", help="刪除整個分類，例如：!delcat 早餐")
    async def delete_category(self, ctx, *, category: str):
        category_key = util.normalize_text(category)
        async with self._lock:
            if category_key in self.data:
                del self.data[category_key]
                await self.save_data()
                await ctx.send(f"🗑️ 已刪除分類「{category}」。")
            else:
                await ctx.send("⚠️ 沒有該分類。")

    @delete_category.error
    async def delete_category_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ 請提供要刪除的分類名稱，例如：`?delcat 早餐`")
        else:
            BotLogger.error("Eat", f"delcat 指令錯誤: {error}")

    # 斜線指令版本
    @app_commands.command(name="eat", description="獲得餐點推薦")
    @app_commands.describe(category="餐點分類 (可選，不填會顯示分類選擇按鈕)")
    async def slash_eat(self, interaction: discord.Interaction, category: str = None):
        """斜線指令版本的 eat"""
        try:
            async with self._lock:
                await self.load_data()
            
            if category is None:
                # 顯示分類選擇UI
                await self._show_category_selection_slash(interaction.user, interaction)
            else:
                # 直接推薦餐點
                await self._show_dish_recommendation_slash(interaction.user, category, interaction)
                
        except Exception as e:
            BotLogger.error("Eat", f"處理slash eat指令時發生錯誤: {e}")
            if interaction.response.is_done():
                await interaction.followup.send("❌ 系統發生錯誤，請稍後再試。", ephemeral=True)
            else:
                await interaction.response.send_message("❌ 系統發生錯誤，請稍後再試。", ephemeral=True)

    @app_commands.command(name="menu", description="查看指定分類的所有餐點選項")
    @app_commands.describe(category="要查看的餐點分類")
    async def slash_menu(self, interaction: discord.Interaction, category: str):
        """斜線指令版本的 menu"""
        category_key = util.normalize_text(category)
        async with self._lock:
            await self.load_data()
            if category_key in self.data and self.data[category_key]:
                items = self.data[category_key]
                embed = discord.Embed(
                    title=f"🍽️ {category} 分類餐點",
                    description=f"共 {len(items)} 項餐點：\n" + "\n".join(f"• {item}" for item in items),
                    color=discord.Color.blue()
                )
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(f"❌ 沒有找到「{category}」分類或該分類為空。", ephemeral=True)

    @app_commands.command(name="categories", description="查看所有可用的餐點分類")
    async def slash_categories(self, interaction: discord.Interaction):
        """斜線指令版本的 categories"""
        async with self._lock:
            await self.load_data()
            if self.data:
                categories_info = []
                for category_key, items in self.data.items():
                    # 從normalized key復原顯示名稱（使用第一個項目推測，或使用key本身）
                    display_name = category_key
                    categories_info.append(f"• **{display_name}** ({len(items)} 項)")
                
                embed = discord.Embed(
                    title="🗂️ 所有餐點分類",
                    description="\n".join(categories_info),
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message("📭 目前沒有任何分類，請先新增一些內容。", ephemeral=True)

    @app_commands.command(name="add_food", description="新增餐點到指定分類")
    @app_commands.describe(
        category="餐點分類",
        item="要新增的餐點名稱"
    )
    async def slash_add_food(self, interaction: discord.Interaction, category: str, item: str):
        """斜線指令版本的 add_food"""
        category_key = util.normalize_text(category)
        async with self._lock:
            await self.load_data()
            if category_key not in self.data:
                self.data[category_key] = []
            
            if item in self.data[category_key]:
                await interaction.response.send_message(f"⚠️ 「{item}」已經在「{category}」分類中了。", ephemeral=True)
            else:
                self.data[category_key].append(item)
                await self.save_data()
                await interaction.response.send_message(f"✅ 已將「{item}」新增到「{category}」分類。")

    @app_commands.command(name="remove_food", description="從指定分類移除餐點")
    @app_commands.describe(
        category="餐點分類",
        item="要移除的餐點名稱"
    )
    async def slash_remove_food(self, interaction: discord.Interaction, category: str, item: str):
        """斜線指令版本的 remove_food"""
        category_key = util.normalize_text(category)
        async with self._lock:
            await self.load_data()
            if category_key in self.data and item in self.data[category_key]:
                self.data[category_key].remove(item)
                if not self.data[category_key]:  # 如果分類變空，刪除分類
                    del self.data[category_key]
                await self.save_data()
                await interaction.response.send_message(f"🗑️ 已從「{category}」分類中移除「{item}」。")
            else:
                await interaction.response.send_message(f"❌ 在「{category}」分類中找不到「{item}」。", ephemeral=True)

    @app_commands.command(name="delete_category", description="刪除整個餐點分類")
    @app_commands.describe(category="要刪除的餐點分類")
    async def slash_delete_category(self, interaction: discord.Interaction, category: str):
        """斜線指令版本的 delete_category"""
        category_key = util.normalize_text(category)
        async with self._lock:
            await self.load_data()
            if category_key in self.data:
                del self.data[category_key]
                await self.save_data()
                await interaction.response.send_message(f"🗑️ 已刪除分類「{category}」。")
            else:
                await interaction.response.send_message(f"❌ 沒有找到「{category}」分類。", ephemeral=True)

    async def _show_category_selection_slash(self, user: discord.User, interaction: discord.Interaction):
        """為斜線指令顯示分類選擇界面"""
        if not self.data:
            await interaction.response.send_message("📭 目前沒有任何分類，請先新增一些內容。", ephemeral=True)
            return

        embed = discord.Embed(
            title="🍽️ 請選擇餐點分類",
            description="點選下方按鈕以獲得該分類的推薦餐點。",
            color=discord.Color.green()
        )
        
        view = CategoryButtonsView(self.data, user)
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    async def _show_dish_recommendation_slash(self, user: discord.User, category: str, interaction: discord.Interaction):
        """為斜線指令顯示餐點推薦"""
        category_key = util.normalize_text(category)
        if category_key not in self.data or not self.data[category_key]:
            await interaction.response.send_message(f"❌ 找不到「{category}」的資料或該分類為空。", ephemeral=True)
            return

        choice = random.choice(self.data[category_key])
        await interaction.response.send_message(f"🍽️ 推薦你點：**{choice}**")

    # 自動完成功能
    async def category_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """分類自動完成"""
        async with self._lock:
            await self.load_data()
            choices = []
            current_lower = current.lower()
            
            for category_key in self.data.keys():
                if current_lower in category_key.lower():
                    # 限制顯示前25個選項
                    if len(choices) < 25:
                        choices.append(app_commands.Choice(name=category_key, value=category_key))
                    else:
                        break
            
            return choices

    async def food_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """食物項目自動完成"""
        # 獲取當前已輸入的分類
        category = interaction.namespace.category if hasattr(interaction.namespace, 'category') else None
        if not category:
            return []
            
        async with self._lock:
            await self.load_data()
            category_key = util.normalize_text(category)
            
            if category_key not in self.data:
                return []
                
            choices = []
            current_lower = current.lower()
            
            for item in self.data[category_key]:
                if current_lower in item.lower():
                    if len(choices) < 25:
                        choices.append(app_commands.Choice(name=item, value=item))
                    else:
                        break
            
            return choices

    # 為相關指令添加自動完成
    slash_eat.autocomplete('category')(category_autocomplete)
    slash_menu.autocomplete('category')(category_autocomplete)
    slash_add_food.autocomplete('category')(category_autocomplete)
    slash_remove_food.autocomplete('category')(category_autocomplete)
    slash_remove_food.autocomplete('item')(food_autocomplete)
    slash_delete_category.autocomplete('category')(category_autocomplete)


async def setup(bot: commands.Bot):
    eat_cog = Eat(bot)
    await eat_cog.initialize()  # 確保資料初始化完成
    await bot.add_cog(eat_cog)
