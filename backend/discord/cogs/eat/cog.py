"""Eat feature cog."""

import asyncio
import json
import logging
import random
from datetime import datetime
from typing import Any, cast

import discord
from config import DATA_DIR
from discord import app_commands
from discord.ext import commands

from .constants import EAT_COLOR, EAT_THUMBNAIL
from .views import CategoryButtonsView, ItemListView, RecommendationView

logger = logging.getLogger(__name__)

EatData = dict[str, Any]


class EatCog(commands.Cog):
    """餐點推薦功能"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_file = DATA_DIR / "eat.json"
        self.global_embed_file = DATA_DIR / "embed.json"
        self.data: EatData = {}
        self.global_embed_config: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._dirty = False

    async def cog_load(self) -> None:
        await self.load_data(log_stats=True)
        await self.load_global_embed()

    async def load_data(self, log_stats: bool = False) -> None:
        try:
            async with self._lock:
                if self.data_file.exists():
                    with open(self.data_file, encoding="utf-8") as f:
                        self.data = json.load(f)

                self.data.setdefault("categories", {})
                self.data.setdefault("recent", {})
                self.data.setdefault(
                    "settings",
                    {
                        "anti_repeat": {"enabled": True, "size": 5},
                        "time_based": {"enabled": True, "mapping": {}},
                    },
                )

                if log_stats:
                    category_count = len(self.data["categories"])
                    item_count = sum(len(items) for items in self.data["categories"].values())
                    logger.info(f"Eat: loaded {category_count} categories, {item_count} items")
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
                with open(self.global_embed_file, encoding="utf-8") as f:
                    self.global_embed_config = json.load(f)
        except Exception as e:
            logger.warning(f"Eat: load global embed failed - {e}")

    # ==================== Helpers ====================

    def create_embed(
        self,
        title: str,
        description: str = "",
        color: discord.Color = EAT_COLOR,
        footer: str | None = None,
    ) -> discord.Embed:
        """建立 Embed"""
        embed = discord.Embed(title=title, description=description, color=color)

        # Author from global embed config
        if author := self.global_embed_config.get("author", {}):
            if author.get("name"):
                embed.set_author(
                    name=author["name"], icon_url=author.get("icon_url"), url=author.get("url")
                )

        embed.set_thumbnail(url=EAT_THUMBNAIL)

        if footer:
            embed.set_footer(text=footer)

        return embed

    def get_category_item_count(self, category: str) -> int:
        """取得分類項目數量"""
        key = self._find_category_key(category)
        if key:
            return len(self.data["categories"].get(key, []))
        return 0

    def _normalize(self, text: str) -> str:
        return text.strip().lower().replace(" ", "")

    def get_time_based_category(self) -> str | None:
        """取得時段推薦分類"""
        settings = self.data.get("settings", {}).get("time_based", {})
        if not settings.get("enabled", False):
            return None
        now = datetime.now().strftime("%H:%M")
        mapping: dict[str, str] = settings.get("mapping", {})
        for time_range, category in mapping.items():
            try:
                start, end = time_range.split("-")
                if start <= now <= end:
                    return category
            except ValueError:
                continue
        return None

    async def get_recommendation(self, category: str, user_id: str) -> str | None:
        """取得推薦"""
        async with self._lock:
            category_key = self._find_category_key(category)
            if category_key and self._normalize(category_key) == "套餐":
                return await self._get_random_combo()

            if not category_key or category_key not in self.data["categories"]:
                return None
            items: list[str] = self.data["categories"][category_key]
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
        """隨機組合：餐點 + 飲料/飲料店"""
        food: list[str] = []
        drinks: list[str] = []
        # 明確定義來源分類
        food_cats = {"正餐", "速食", "小吃"}
        drink_cats = {"飲料", "飲料店"}

        for cat, items in self.data["categories"].items():
            if cat in food_cats:
                food.extend(items)
            elif cat in drink_cats:
                drinks.extend(items)

        f = random.choice(food) if food else "主餐"
        d = random.choice(drinks) if drinks else "水"
        return f"{f} + {d}"

    def _find_category_key(self, category: str) -> str | None:
        norm = self._normalize(category)
        for key in self.data["categories"]:
            if self._normalize(key) == norm:
                return cast(str, key)
        return None

    # ==================== Autocomplete ====================

    async def _category_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        cl = current.lower()
        return [
            app_commands.Choice(name=k, value=k)
            for k in self.data.get("categories", {})
            if cl in k.lower()
        ][:25]

    async def _item_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        cat: str | None = getattr(interaction.namespace, "category", None)
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
        self, interaction: discord.Interaction, category: str | None = None
    ) -> None:
        """主要 UI 指令：顯示分類按鈕或直接推薦"""
        await self.load_data()

        if not category:
            if not self.data["categories"]:
                await interaction.response.send_message("目前無資料", ephemeral=True)
                return

            time_category = self.get_time_based_category()
            total = len(self.data["categories"])
            desc = "點選分類獲得推薦"
            if time_category:
                desc += f"\n時段推薦：**{time_category}**"

            embed = self.create_embed(
                title="今天吃什麼", description=desc, footer=f"{total} 個分類"
            )
            view: discord.ui.View = CategoryButtonsView(self, interaction.user, time_category)
            await interaction.response.send_message(embed=embed, view=view)
            return

        choice = await self.get_recommendation(category, str(interaction.user.id))
        if choice:
            item_count = self.get_category_item_count(category)
            embed = self.create_embed(
                title=f"{category} 推薦", description=f"**{choice}**", footer=f"{item_count} 項可選"
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
            await interaction.response.send_message("目前沒有任何分類", ephemeral=True)
            return

        total_items = sum(len(v) for v in self.data["categories"].values())
        lines = [f"**{cat}** - {len(items)} 項" for cat, items in self.data["categories"].items()]
        embed = self.create_embed(
            title="分類總覽",
            description="\n".join(lines),
            footer=f"{len(self.data['categories'])} 分類 / {total_items} 項",
        )
        await interaction.response.send_message(embed=embed)

    @food_group.command(name="show", description="顯示分類內的項目")
    @app_commands.describe(category="分類名稱")
    async def food_show(self, interaction: discord.Interaction, category: str) -> None:
        """顯示分類內容"""
        await self.load_data()

        key = self._find_category_key(category)
        if not key:
            await interaction.response.send_message("找不到該分類", ephemeral=True)
            return

        items = sorted(self.data["categories"][key])
        if not items:
            await interaction.response.send_message("該分類目前沒有項目", ephemeral=True)
            return

        if len(items) <= 10:
            # 少於 10 項直接顯示
            desc = "\n".join(f"• {i}" for i in items)
            embed = self.create_embed(
                title=f"{key} 清單", description=desc, footer=f"共 {len(items)} 項"
            )
            await interaction.response.send_message(embed=embed)
        else:
            # 超過 10 項使用分頁
            view = ItemListView(self, key, items)
            await interaction.response.send_message(embed=view.get_embed(), view=view)

    @food_group.command(name="add", description="新增餐點")
    @app_commands.describe(category="分類名稱", item="項目名稱")
    @app_commands.default_permissions(manage_messages=True)
    async def food_add(self, interaction: discord.Interaction, category: str, item: str) -> None:
        """新增項目"""
        async with self._lock:
            await self.load_data()
            key = self._find_category_key(category) or category
            items = self.data["categories"].setdefault(key, [])
            if any(self._normalize(i) == self._normalize(item) for i in items):
                await interaction.response.send_message("該項目已存在", ephemeral=True)
                return
            items.append(item)
            await self.save_data()
            embed = self.create_embed(
                title="新增成功",
                description=f"**{item}** → {key}",
                color=discord.Color.green(),
                footer=f"目前 {key} 共 {len(items)} 項",
            )
            await interaction.response.send_message(embed=embed)

    @food_group.command(name="remove", description="移除餐點")
    @app_commands.describe(category="分類名稱", item="項目名稱")
    @app_commands.default_permissions(manage_messages=True)
    async def food_remove(self, interaction: discord.Interaction, category: str, item: str) -> None:
        """移除項目"""
        async with self._lock:
            await self.load_data()
            key = self._find_category_key(category)
            if key:
                items: list[str] = self.data["categories"][key]
                norm_item = self._normalize(item)
                for idx, val in enumerate(items):
                    if self._normalize(val) == norm_item:
                        items.pop(idx)
                        category_deleted = not items
                        if category_deleted:
                            del self.data["categories"][key]
                        await self.save_data()
                        desc = f"~~{val}~~ ← {key}"
                        if category_deleted:
                            desc += "\n\n*分類已清空並刪除*"
                        embed = self.create_embed(
                            title="移除成功",
                            description=desc,
                            color=discord.Color.orange(),
                            footer=None if category_deleted else f"目前 {key} 剩餘 {len(items)} 項",
                        )
                        await interaction.response.send_message(embed=embed)
                        return
            await interaction.response.send_message("找不到該項目", ephemeral=True)

    @food_group.command(name="delete", description="刪除整個分類")
    @app_commands.describe(category="分類名稱")
    @app_commands.default_permissions(administrator=True)
    async def food_delete(self, interaction: discord.Interaction, category: str) -> None:
        """刪除分類"""
        async with self._lock:
            await self.load_data()
            key = self._find_category_key(category)
            if key:
                item_count = len(self.data["categories"][key])
                del self.data["categories"][key]
                await self.save_data()
                embed = self.create_embed(
                    title="分類已刪除",
                    description=f"~~{key}~~ ({item_count} 項)",
                    color=discord.Color.red(),
                )
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message("找不到該分類", ephemeral=True)
