import asyncio
import os
import random

import discord
from discord.ext import commands

from utils.util import normalize_text, read_json, write_json

DATA_DIR = "./data"
DATA_FILE = os.path.join(DATA_DIR, "eat.json")


class Eat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = {}
        self._lock = asyncio.Lock()          # ← add

    async def initialize(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        raw = await read_json(DATA_FILE)
        self.data = raw if isinstance(raw, dict) else {}

    async def save_data(self):
        await write_json(DATA_FILE, self.data)

    @commands.Cog.listener()
    async def on_ready(self):
        await self.initialize()

    @commands.command(aliases=["點"], help="幫你想要吃什麼")
    async def eat(self, ctx: commands.Context, category: str = None):
        if not category:
            await ctx.send("❓ 要吃什麼？請輸入 `!eat 類別`，例如 `!eat 主餐`")
            return

        category_key = normalize_text(category)

        if category_key in self.data:
            options = self.data[category_key]
            if options:
                choice = random.choice(options)
                await ctx.send(f"🍽️ 推薦你點：**{choice}**")
            else:
                await ctx.send(f"⚠️ 「{category}」的選項是空的！")
        else:
            await ctx.send(f"❌ 找不到「{category}」的資料。")

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
        category_key = normalize_text(category)
        item_key = normalize_text(item)
        async with self._lock:
            self.data.setdefault(category_key, [])
            # 先將現有選項正規化比對，避免重複
            normalized_items = [normalize_text(x)
                                for x in self.data[category_key]]
            if item_key in normalized_items:
                await ctx.send("⚠️ 該選項已存在。")
                return
            self.data[category_key].append(item)
            await self.save_data()
        await ctx.send(f"✅ 已將「{item}」新增到「{category}」中。")

    @commands.command(name="delitem", help="從分類中移除選項，例如：!delitem 主餐 蛋餅")
    async def remove_eat(self, ctx, category: str, *, item: str):
        category_key = normalize_text(category)
        item_key = normalize_text(item)
        async with self._lock:
            if category_key in self.data:
                # 找出符合正規化的項目原文索引
                for idx, existing_item in enumerate(self.data[category_key]):
                    if normalize_text(existing_item) == item_key:
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
        category_key = normalize_text(category)
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
        category_key = normalize_text(category)
        async with self._lock:
            if category_key in self.data:
                del self.data[category_key]
                await self.save_data()
                await ctx.send(f"🗑️ 已刪除分類「{category}」。")
            else:
                await ctx.send("⚠️ 沒有該分類。")


async def setup(bot: commands.Bot):
    await bot.add_cog(Eat(bot))
