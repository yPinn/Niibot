import os
import random

import discord
from discord.ext import commands

from utils.util import read_json, write_json

DATA_DIR = "./data"
DATA_FILE = os.path.join(DATA_DIR, "eat.json")


class Eat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = {}

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
            await ctx.send("❓ 要吃什麼？請輸入 `!eat 類別`，例如 `!eat 早餐`")
            return

        category_key = category.strip().lower()

        if category_key in self.data:
            options = self.data[category_key]
            if options:
                choice = random.choice(options)
                await ctx.send(f"🍽️ 推薦你點：**{choice}**")
            else:
                await ctx.send(f"⚠️ 「{category}」的選項是空的！")
        else:
            await ctx.send(f"❌ 找不到「{category}」的資料。")

    @commands.command(name="menu", help="菜單")
    async def eat_list(self, ctx: commands.Context):
        if not self.data:
            await ctx.send("📭 目前沒有任何分類，請先新增一些內容。")
            return

        categories = sorted(self.data.keys())
        embed = discord.Embed(title="📋 可用分類列表", color=discord.Color.blue())
        embed.description = "\n".join(f"- {cat}" for cat in categories)

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Eat(bot))
