import json
import os
import random

import discord
from discord.ext import commands

DATA_FILE = "./data/eat.json"


class Eat(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = self.load_data()

    def load_data(self):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)

    # 前綴指令
    @commands.command(help="幫你想要吃什麼")
    async def eat(self, ctx: commands.Context, category: str = None):
        if category is None:
            await ctx.send("要吃什麼？請輸入 `!eat 類別` 例如 `!eat 早餐`")
            return

        category = category.strip().lower()

        if category in self.data:
            options = self.data[category]
            if options:
                choice = random.choice(options)
                await ctx.send(f"推薦你吃：**{choice}**")
            else:
                await ctx.send(f"「{category}」的選項是空的！")
        else:
            await ctx.send(f"找不到「{category}」的資料。")

    @commands.command(name="menu", help="菜單")
    async def eat_list(self, ctx: commands.Context):
        if not self.data:
            await ctx.send("目前沒有任何分類，請先新增一些內容。")
            return

        categories = list(self.data.keys())
        formatted = "\n".join(f"- {cat}" for cat in categories)
        await ctx.send(f"📋 可用分類如下：\n{formatted}")

    # 自然語言監聽
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return

        if message.content.lower() == "吃什麼":
            await message.channel.send("要吃什麼？你也可以輸入 `!eat 類別` 試試看！")


async def setup(bot: commands.Bot):
    await bot.add_cog(Eat(bot))
