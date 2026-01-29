"""Eat feature cog."""

import asyncio
import json
import logging
import random
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, cast

from config import DATA_DIR
from discord.ext import commands

import discord
from discord import app_commands

from .constants import EAT_COLOR
from .views import CategoryButtonsView, RecommendationView

logger = logging.getLogger(__name__)

EatData = Dict[str, Any]


class EatCog(commands.Cog):
    """餐點推薦功能"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_file = DATA_DIR / "eat.json"
        self.global_embed_file = DATA_DIR / "embed.json"
        self.data: EatData = {}
        self.global_embed_config: Dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._dirty = False

    async def cog_load(self) -> None:
        await self.load_data(log_stats=True)
        await self.load_global_embed()

    async def load_data(self, log_stats: bool = False) -> None:
        try:
            async with self._lock:
                if self.data_file.exists():
                    with open(self.data_file, "r", encoding="utf-8") as f:
                        self.data = json.load(f)

                self.data.setdefault("categories", {})
                self.data.setdefault("recent", {})
                self.data.setdefault("settings", {
                    "anti_repeat": {"enabled": True, "size": 5},
                    "time_based": {"enabled": True, "mapping": {}}
                })

                if log_stats:
                    category_count = len(self.data["categories"])
                    item_count = sum(len(items)
                                     for items in self.data["categories"].values())
                    logger.info(
                        f"Eat: loaded {category_count} categories, {item_count} items")
        except Exception as e:
            logger.error(f"Eat: load failed - {e}")

    async def save_data(self) -> None:
        try:
            async with self._lock:
                with open(self.data_file, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
                self._dirty = False
        except Exception as e:
            logger.error(f"Eat: save failed - {e}")

    async def load_global_embed(self) -> None:
        try:
            if self.global_embed_file.exists():
                with open(self.global_embed_file, "r", encoding="utf-8") as f:
                    self.global_embed_config = json.load(f)
        except Exception as e:
            logger.warning(f"Eat: load global embed failed - {e}")

    # ==================== Helpers ====================

    def create_embed(
        self,
        title: str,
        description: str = "",
        color: discord.Color = EAT_COLOR
    ) -> discord.Embed:
        """建立 Embed"""
        embed = discord.Embed(title=title, description=description, color=color)
        eat_embed = self.data.get("embed", {})
        eat_author = eat_embed.get("author", {})
        global_author = self.global_embed_config.get("author", {})

        author_name = eat_author.get("name") or global_author.get("name")
        if author_name:
            embed.set_author(
                name=author_name,
                icon_url=eat_author.get("icon_url") or global_author.get("icon_url"),
                url=eat_author.get("url") or global_author.get("url")
            )

        if eat_embed.get("thumbnail"):
            embed.set_thumbnail(url=eat_embed["thumbnail"])

        return embed

    def _normalize(self, text: str) -> str:
        return text.strip().lower().replace(" ", "")

    def get_time_based_category(self) -> Optional[str]:
        """取得時段推薦分類"""
        settings = self.data.get("settings", {}).get("time_based", {})
        if not settings.get("enabled", False):
            return None
        now = datetime.now().strftime("%H:%M")
        mapping: Dict[str, str] = settings.get("mapping", {})
        for time_range, category in mapping.items():
            try:
                start, end = time_range.split("-")
                if start <= now <= end:
                    return category
            except ValueError:
                continue
        return None

    async def get_recommendation(self, category: str, user_id: str) -> Optional[str]:
        """取得推薦"""
        async with self._lock:
            category_key = self._find_category_key(category)
            if category_key and self._normalize(category_key) == "隨機套餐":
                return await self._get_random_combo()

            if not category_key or category_key not in self.data["categories"]:
                return None
            items: List[str] = self.data["categories"][category_key]
            if not items:
                return None

            anti_repeat = self.data["settings"]["anti_repeat"]
            if anti_repeat.get("enabled", True):
                user_recent = self.data["recent"].setdefault(user_id, {})
                recent_items = user_recent.setdefault(category_key, [])
                available = [i for i in items if i not in recent_items]
                if not available:
                    available = items
                    recent_items.clear()
                choice = random.choice(available)
                recent_items.append(choice)
                if len(recent_items) > anti_repeat.get("size", 5):
                    recent_items.pop(0)
                self._dirty = True
                return choice
            return random.choice(items)

    async def _get_random_combo(self) -> str:
        food: List[str] = []
        drinks: List[str] = []
        for cat, items in self.data["categories"].items():
            norm = self._normalize(cat)
            if "飲料" in norm:
                drinks.extend(items)
            elif norm != "隨機套餐":
                food.extend(items)
        f = random.choice(food) if food else "主餐"
        d = random.choice(drinks) if drinks else "水"
        return f"{f} + {d}"

    def _find_category_key(self, category: str) -> Optional[str]:
        norm = self._normalize(category)
        for key in self.data["categories"]:
            if self._normalize(key) == norm:
                return cast(str, key)
        return None

    # ==================== Autocomplete ====================

    async def _category_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        cl = current.lower()
        return [
            app_commands.Choice(name=k, value=k)
            for k in self.data.get("categories", {})
            if cl in k.lower()
        ][:25]

    async def _item_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        cat: Optional[str] = getattr(interaction.namespace, "category", None)
        key = self._find_category_key(cat) if cat else None
        if not key:
            return []
        cl = current.lower()
        return [
            app_commands.Choice(name=i, value=i)
            for i in self.data["categories"][key]
            if cl in i.lower()
        ][:25]

    # ==================== Main UI Command ====================

    @app_commands.command(name="eat", description="餐點推薦")
    @app_commands.describe(category="直接指定分類")
    async def eat_command(
        self, interaction: discord.Interaction, category: Optional[str] = None
    ) -> None:
        """主要 UI 指令：顯示分類按鈕或直接推薦"""
        await self.load_data()

        if not category:
            if not self.data["categories"]:
                await interaction.response.send_message("目前無資料", ephemeral=True)
                return

            time_category = self.get_time_based_category()
            description = "點選下方按鈕以獲得該分類的推薦餐點"
            if time_category and time_category in self.data["categories"]:
                description += f"\n\n> **目前時段推薦：{time_category}**"

            embed = self.create_embed(title="請選擇餐點分類", description=description)
            view = CategoryButtonsView(self, interaction.user)
            await interaction.response.send_message(embed=embed, view=view)
            return

        choice = await self.get_recommendation(category, str(interaction.user.id))
        if choice:
            embed = self.create_embed(
                title=f"{category} 推薦",
                description=f"**{choice}**"
            )
            view = RecommendationView(self, category, interaction.user)
            await interaction.response.send_message(embed=embed, view=view)
            if self._dirty:
                await self.save_data()
        else:
            await interaction.response.send_message("找不到該分類", ephemeral=True)

    # ==================== Management Commands ====================

    food_group = app_commands.Group(name="food", description="餐點管理指令")

    @food_group.command(name="cat", description="列出所有分類")
    async def food_cat(self, interaction: discord.Interaction) -> None:
        """列出所有分類"""
        await self.load_data()

        if not self.data["categories"]:
            await interaction.response.send_message("無分類", ephemeral=True)
            return

        embed = self.create_embed(title="所有餐點分類")
        for cat, items in cast(Dict[str, List[str]], self.data["categories"]).items():
            embed.add_field(name=cat, value=f"{len(items)} 項", inline=True)
        await interaction.response.send_message(embed=embed)

    @food_group.command(name="show", description="顯示分類內的項目")
    @app_commands.describe(category="分類名稱")
    async def food_show(self, interaction: discord.Interaction, category: str) -> None:
        """顯示分類內容"""
        await self.load_data()

        key = self._find_category_key(category)
        if key:
            items = sorted(self.data["categories"][key])
            embed = self.create_embed(
                title=f"{key} 菜單",
                description="\n".join(f"- {i}" for i in items)
            )
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("找不到分類", ephemeral=True)

    @food_group.command(name="add", description="新增餐點")
    @app_commands.describe(category="分類名稱", item="項目名稱")
    @app_commands.default_permissions(manage_messages=True)
    async def food_add(
        self, interaction: discord.Interaction, category: str, item: str
    ) -> None:
        """新增項目"""
        async with self._lock:
            await self.load_data()
            key = self._find_category_key(category) or category
            items = self.data["categories"].setdefault(key, [])
            if any(self._normalize(i) == self._normalize(item) for i in items):
                await interaction.response.send_message("項目已存在", ephemeral=True)
                return
            items.append(item)
            await self.save_data()
            await interaction.response.send_message(f"已新增「{item}」至「{key}」")

    @food_group.command(name="remove", description="移除餐點")
    @app_commands.describe(category="分類名稱", item="項目名稱")
    @app_commands.default_permissions(manage_messages=True)
    async def food_remove(
        self, interaction: discord.Interaction, category: str, item: str
    ) -> None:
        """移除項目"""
        async with self._lock:
            await self.load_data()
            key = self._find_category_key(category)
            if key:
                items: List[str] = self.data["categories"][key]
                norm_item = self._normalize(item)
                for idx, val in enumerate(items):
                    if self._normalize(val) == norm_item:
                        items.pop(idx)
                        if not items:
                            del self.data["categories"][key]
                        await self.save_data()
                        await interaction.response.send_message(f"已移除 {val}")
                        return
            await interaction.response.send_message("找不到項目", ephemeral=True)

    @food_group.command(name="delete", description="刪除整個分類")
    @app_commands.describe(category="分類名稱")
    @app_commands.default_permissions(administrator=True)
    async def food_delete(
        self, interaction: discord.Interaction, category: str
    ) -> None:
        """刪除分類"""
        async with self._lock:
            await self.load_data()
            key = self._find_category_key(category)
            if key:
                del self.data["categories"][key]
                await self.save_data()
                await interaction.response.send_message(f"已刪除分類 {key}")
            else:
                await interaction.response.send_message("找不到分類", ephemeral=True)
