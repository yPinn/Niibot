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
        """逾時時將所有按鈕變灰並禁用"""
        try:
            BotLogger.debug(
                "Eat", f"CategoryButtonsView 超時觸發，message: {self.message is not None}")

            # 禁用所有按鈕
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
                    item.style = discord.ButtonStyle.grey

            if self.message:
                embed = discord.Embed(
                    title="🍽️ 請選擇餐點分類",
                    description="⏰ 操作已逾時，請重新使用指令",
                    color=discord.Color.light_grey()
                )
                await self.message.edit(embed=embed, view=self)
                BotLogger.debug("Eat", "CategoryButtonsView 超時更新成功")
            else:
                BotLogger.warning(
                    "Eat", "CategoryButtonsView 超時時 message 為 None，無法更新 UI")
        except discord.NotFound:
            BotLogger.debug("Eat", "CategoryButtonsView 超時更新失敗：訊息已被刪除")
        except discord.HTTPException as e:
            BotLogger.error("Eat", f"CategoryButtonsView 超時更新失敗 (HTTP): {e}")
        except Exception as e:
            BotLogger.error("Eat", f"CategoryButtonsView 超時處理失敗: {e}")


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
        await interaction.response.edit_message(embed=embed, view=None)
        # 先編輯訊息，再取得回應並設置到新 view
        response_message = await interaction.original_response()
        view = DishButtonsView(self.category, options,
                               interaction.user, response_message)
        await response_message.edit(embed=embed, view=view)


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
        try:
            BotLogger.debug(
                "Eat", f"DishButtonsView 超時觸發，message: {self.message is not None}")

            # 禁用所有按鈕
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
                    item.style = discord.ButtonStyle.grey

            if self.message:
                # 保持原有的 embed 內容但改變顏色
                old_embed = self.message.embeds[0] if self.message.embeds else None
                if old_embed:
                    embed = discord.Embed(
                        title=old_embed.title,
                        description=f"{old_embed.description}\n\n⏰ 操作已逾時，請重新使用指令",
                        color=discord.Color.light_grey()
                    )
                else:
                    embed = discord.Embed(
                        title="🍽️ 餐點推薦",
                        description="⏰ 操作已逾時，請重新使用指令",
                        color=discord.Color.light_grey()
                    )
                await self.message.edit(embed=embed, view=self)
                BotLogger.debug("Eat", "DishButtonsView 超時更新成功")
            else:
                BotLogger.warning(
                    "Eat", "DishButtonsView 超時時 message 為 None，無法更新 UI")
        except discord.NotFound:
            BotLogger.debug("Eat", "DishButtonsView 超時更新失敗：訊息已被刪除")
        except discord.HTTPException as e:
            BotLogger.error("Eat", f"DishButtonsView 超時更新失敗 (HTTP): {e}")
        except Exception as e:
            BotLogger.error("Eat", f"DishButtonsView 超時處理失敗: {e}")


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
        await interaction.response.edit_message(embed=embed, view=None)
        # 先編輯訊息，再取得回應並設置到新 view
        response_message = await interaction.original_response()
        view = DishButtonsView(self.category, self.options,
                               interaction.user, response_message)
        await response_message.edit(embed=embed, view=view)


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
        await interaction.response.edit_message(embed=embed, view=None)
        # 先編輯訊息，再取得回應並設置到新 view
        response_message = await interaction.original_response()
        view = CategoryButtonsView(
            cog.data, interaction.user, response_message)
        await response_message.edit(embed=embed, view=view)


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

    # 文字指令：!eat 類別
    @commands.command(aliases=["點"], help="幫你想要吃什麼，使用方法：!eat 類別 或 !eat")
    async def eat(self, ctx: commands.Context, *, category: str = None):
        if category is None:
            # 無參數時，送出 embed + 分類按鈕介面
            if not self.data:
                await ctx.send("📭 目前沒有任何分類，請先新增一些內容。")
                return

            embed = discord.Embed(
                title="🍽️ 請選擇餐點分類",
                description="點選下方按鈕以獲得該分類的推薦餐點。",
                color=discord.Color.green()
            )
            message = await ctx.send(embed=embed, view=None, reference=ctx.message, mention_author=False)
            view = CategoryButtonsView(self.data, ctx.author, message)
            await message.edit(embed=embed, view=view)
        else:
            # 有參數時，舊版隨機抽餐點
            category_key = util.normalize_text(category)
            if category_key in self.data and self.data[category_key]:
                choice = random.choice(self.data[category_key])
                await ctx.send(f"🍽️ 推薦你點：**{choice}**")
            else:
                await ctx.send(f"❌ 找不到「{category}」的資料或該分類為空。")

    async def category_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """分類自動完成功能"""
        try:
            # 獲取所有分類並過濾符合當前輸入的選項
            categories = list(self.data.keys())
            filtered = [cat for cat in categories if current.lower(
            ) in cat.lower()][:25]  # Discord限制最多25個選項
            return [app_commands.Choice(name=cat, value=cat) for cat in filtered]
        except Exception as e:
            BotLogger.error("Eat", f"自動完成功能錯誤: {e}")
            return []

    # 斜線指令版本
    @app_commands.command(name="eat", description="幫你選擇要吃什麼")
    @app_commands.describe(category="餐點分類（可選）")
    @app_commands.autocomplete(category=category_autocomplete)
    async def eat_slash(self, interaction: discord.Interaction, category: str = None):
        """斜線指令版本的eat指令"""
        if category is None:
            # 無參數時，送出 embed + 分類按鈕介面
            if not self.data:
                await interaction.response.send_message("📭 目前沒有任何分類，請先新增一些內容。", ephemeral=True)
                return

            embed = discord.Embed(
                title="🍽️ 請選擇餐點分類",
                description="點選下方按鈕以獲得該分類的推薦餐點。",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, view=None)
            # 取得回應訊息並設置view
            response_message = await interaction.original_response()
            view = CategoryButtonsView(
                self.data, interaction.user, response_message)
            await response_message.edit(embed=embed, view=view)
        else:
            # 有參數時，隨機抽餐點
            category_key = util.normalize_text(category)
            if category_key in self.data and self.data[category_key]:
                choice = random.choice(self.data[category_key])
                await interaction.response.send_message(f"🍽️ 推薦你點：**{choice}**")
            else:
                await interaction.response.send_message(f"❌ 找不到「{category}」的資料或該分類為空。", ephemeral=True)

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

    @commands.command(name="menu", help="顯示某分類的所有選項，例如：!menu 主餐")
    async def show_eat(self, ctx, *, category: str):
        if not category:
            await ctx.send("❓ 要吃什麼？請輸入 `!menu 類別`，例如 `!menu 主餐`")
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


async def setup(bot: commands.Bot):
    eat_cog = Eat(bot)
    await eat_cog.initialize()  # 確保資料初始化完成
    await bot.add_cog(eat_cog)
