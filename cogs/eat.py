import asyncio
import os
import random

import discord
from discord.ext import commands

from utils import util

DATA_DIR = "./data"
DATA_FILE = os.path.join(DATA_DIR, "eat.json")


class Eat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = {}
        self._lock = asyncio.Lock()

    async def initialize(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        raw = await util.read_json(DATA_FILE)
        self.data = raw if isinstance(raw, dict) else {}

    async def save_data(self):
        await util.write_json(DATA_FILE, self.data)

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
            view = self.CategoryButtonsView(self.data, ctx.author)
            await ctx.send(embed=embed, view=view, reference=ctx.message, mention_author=False)
        else:
            # 有參數時，舊版隨機抽餐點
            category_key = util.normalize_text(category)
            if category_key in self.data and self.data[category_key]:
                choice = random.choice(self.data[category_key])
                await ctx.send(f"🍽️ 推薦你點：**{choice}**")
            else:
                await ctx.send(f"❌ 找不到「{category}」的資料或該分類為空。")

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

    # 以下是按鈕的 View 與按鈕定義

    class CategoryButtonsView(discord.ui.View):
        def __init__(self, data: dict, user: discord.User):
            super().__init__(timeout=120)
            self.data = data
            self.user = user
            # 一次最多顯示25個按鈕（Discord限制）
            count = 0
            for category in sorted(data.keys()):
                if count >= 25:
                    break
                self.add_item(Eat.CategoryButton(category))
                count += 1

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            # 限制只能原使用者使用按鈕
            if interaction.user.id != self.user.id:
                await interaction.response.send_message(
                    "❌ 這些按鈕只能由原始命令使用者操作。", ephemeral=True)
                return False
            return True

    class CategoryButton(discord.ui.Button):
        def __init__(self, category: str):
            super().__init__(label=category, style=discord.ButtonStyle.primary)
            self.category = category

        async def callback(self, interaction: discord.Interaction):
            # 點擊後送該分類隨機餐點 + 換一個按鈕
            if not self.view or not hasattr(self.view, 'data'):
                await interaction.response.send_message("資料錯誤，請稍後再試。", ephemeral=True)
                return

            options = self.view.data.get(self.category)
            if not options:
                await interaction.response.send_message(f"❌ 「{self.category}」分類沒有餐點。", ephemeral=True)
                return

            choice = random.choice(options)

            embed = discord.Embed(
                title=f"🍽️ {self.category} 推薦餐點",
                description=f"**{choice}**",
                color=discord.Color.blurple()
            )
            view = Eat.DishButtonsView(
                self.category, options, interaction.user)
            await interaction.response.edit_message(embed=embed, view=view)

    class DishButtonsView(discord.ui.View):
        def __init__(self, category: str, options: list[str], user: discord.User):
            super().__init__(timeout=120)
            self.category = category
            self.options = options
            self.user = user
            self.add_item(Eat.ReloadButton(category, options, user))
            self.add_item(Eat.BackButton(user))

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            # 限制只能原使用者使用按鈕
            if interaction.user.id != self.user.id:
                await interaction.response.send_message(
                    "❌ 這些按鈕只能由原始命令使用者操作。", ephemeral=True)
                return False
            return True

    class ReloadButton(discord.ui.Button):
        def __init__(self, category: str, options: list[str], user: discord.User):
            super().__init__(label="換一個", style=discord.ButtonStyle.success)
            self.category = category
            self.options = options
            self.user = user

        async def callback(self, interaction: discord.Interaction):
            choice = random.choice(self.options)
            embed = discord.Embed(
                title=f"🍽️ {self.category} 推薦餐點",
                description=f"**{choice}**",
                color=discord.Color.blurple()
            )
            # 保留按鈕
            view = Eat.DishButtonsView(self.category, self.options, self.user)
            await interaction.response.edit_message(embed=embed, view=view)

    class BackButton(discord.ui.Button):
        def __init__(self, user: discord.User):
            super().__init__(label="回分類列表", style=discord.ButtonStyle.secondary)
            self.user = user

        async def callback(self, interaction: discord.Interaction):
            if not self.view or not hasattr(self.view, 'user'):
                await interaction.response.send_message("資料錯誤，請稍後再試。", ephemeral=True)
                return
            # 回到分類按鈕列表
            # 重新讀取資料 (假設 data 有變化也可反映)
            bot = interaction.client
            cog = bot.get_cog("Eat")
            if cog is None:
                await interaction.response.send_message("資料錯誤，請稍後再試。", ephemeral=True)
                return
            embed = discord.Embed(
                title="🍽️ 請選擇餐點分類",
                description="點選下方按鈕以獲得該分類的推薦餐點。",
                color=discord.Color.green()
            )
            view = cog.CategoryButtonsView(cog.data, self.user)
            await interaction.response.edit_message(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Eat(bot))
