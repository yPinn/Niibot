"""
餐點推薦功能 Cog
提供智能餐點推薦與管理，支援 Mypy 靜態型別檢查
"""

import asyncio
import json
import logging
import random
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, cast

from config import DATA_DIR
from discord.ext import commands

import discord
from discord import app_commands, ui

logger = logging.getLogger(__name__)

# --- 自定義型別標註 ---
EatData = Dict[str, Any]


class CategoryButton(ui.Button):
    """自定義分類按鈕，解決 Mypy 對 callback 賦值的錯誤"""

    def __init__(self, cog: "Eat", category: str, user: Union[discord.User, discord.Member]):
        super().__init__(
            label=category,
            style=discord.ButtonStyle.primary,
            custom_id=f"cat_{category}"
        )
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
                f"找不到「{self.category}」的資料或該分類為空", ephemeral=True
            )
            return

        embed = self.cog._create_embed(
            title=f"{self.category} 推薦",
            description=f"**{choice}**"
        )
        view = RecommendationView(self.cog, self.category, self.user)
        await interaction.response.edit_message(embed=embed, view=view)


class CategoryButtonsView(ui.View):
    """分類選擇按鈕視圖"""

    def __init__(self, cog: "Eat", user: Union[discord.User, discord.Member]):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user
        self._add_category_buttons()

    def _add_category_buttons(self) -> None:
        """動態添加分類按鈕"""
        categories: List[str] = list(
            self.cog.data.get("categories", {}).keys())[:25]
        for category in categories:
            self.add_item(CategoryButton(self.cog, category, self.user))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("這不是你的選單", ephemeral=True)
            return False
        return True


class RecommendationView(ui.View):
    """推薦結果視圖（換一個、返回）"""

    def __init__(self, cog: "Eat", category: str, user: Union[discord.User, discord.Member]):
        super().__init__(timeout=300)
        self.cog = cog
        self.category = category
        self.user = user

    @ui.button(label="換一個", style=discord.ButtonStyle.success)
    async def reload_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("這不是你的選單", ephemeral=True)
            return

        choice = await self.cog.get_recommendation(self.category, str(interaction.user.id))
        if not choice:
            await interaction.response.send_message(f"找不到「{self.category}」的資料", ephemeral=True)
            return

        embed = self.cog._create_embed(
            title=f"{self.category} 推薦", description=f"**{choice}**")
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="回分類列表", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("這不是你的選單", ephemeral=True)
            return

        time_category = self.cog._get_time_based_category()
        description = "點選下方按鈕以獲得該分類的推薦餐點"
        if time_category and time_category in self.cog.data["categories"]:
            description += f"\n\n> **目前時段推薦：{time_category}**"

        embed = self.cog._create_embed(
            title="請選擇餐點分類", description=description)
        await interaction.response.edit_message(embed=embed, view=CategoryButtonsView(self.cog, self.user))


class Eat(commands.Cog):
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
                        f"Eat: 成功載入 {category_count} 分類，共 {item_count} 項目")
        except Exception as e:
            logger.error(f"Eat: 載入失敗 - {e}")

    async def save_data(self) -> None:
        try:
            async with self._lock:
                with open(self.data_file, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
                self._dirty = False
        except Exception as e:
            logger.error(f"Eat: 保存失敗 - {e}")

    async def load_global_embed(self) -> None:
        try:
            if self.global_embed_file.exists():
                with open(self.global_embed_file, "r", encoding="utf-8") as f:
                    self.global_embed_config = json.load(f)
        except Exception as e:
            logger.warning(f"Eat: 載入全域 Embed 失敗 - {e}")

    def _create_embed(self, title: str, description: str = "", color: discord.Color = discord.Color.blue()) -> discord.Embed:
        embed = discord.Embed(
            title=title, description=description, color=color)
        eat_embed = self.data.get("embed", {})
        eat_author = eat_embed.get("author", {})
        eat_footer = eat_embed.get("footer", {})
        global_author = self.global_embed_config.get("author", {})
        global_footer = self.global_embed_config.get("footer", {})

        author_name = eat_author.get("name") or global_author.get("name")
        if author_name:
            embed.set_author(
                name=author_name,
                icon_url=eat_author.get(
                    "icon_url") or global_author.get("icon_url"),
                url=eat_author.get("url") or global_author.get("url")
            )

        if eat_embed.get("thumbnail"):
            embed.set_thumbnail(url=eat_embed["thumbnail"])

        footer_text = eat_footer.get("text") or global_footer.get("text")
        if footer_text:
            embed.set_footer(
                text=footer_text,
                icon_url=eat_footer.get(
                    "icon_url") or global_footer.get("icon_url")
            )
        return embed

    def _normalize(self, text: str) -> str:
        return text.strip().lower().replace(" ", "")

    def _get_time_based_category(self) -> Optional[str]:
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

    # --- 斜線指令 ---
    @app_commands.command(name="eat", description="獲得餐點推薦")
    async def slash_eat(self, interaction: discord.Interaction, category: Optional[str] = None) -> None:
        await self.load_data()
        if not category:
            if not self.data["categories"]:
                await interaction.response.send_message("目前無資料", ephemeral=True)
                return
            await interaction.response.send_message(embed=self._create_embed(title="請選擇分類"), view=CategoryButtonsView(self, interaction.user))
            return
        choice = await self.get_recommendation(category, str(interaction.user.id))
        if choice:
            await interaction.response.send_message(embed=self._create_embed(title=f"{category} 推薦", description=f"**{choice}**"))
            if self._dirty:
                await self.save_data()
        else:
            await interaction.response.send_message("找不到該分類", ephemeral=True)

    @app_commands.command(name="categories", description="查看所有分類")
    async def slash_categories(self, interaction: discord.Interaction) -> None:
        await self.load_data()
        if not self.data["categories"]:
            await interaction.response.send_message("無分類", ephemeral=True)
            return
        embed = self._create_embed(title="所有餐點分類")
        for cat, items in cast(Dict[str, List[str]], self.data["categories"]).items():
            embed.add_field(name=cat, value=f"{len(items)} 項", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="menu", description="查看分類菜單")
    async def slash_menu(self, interaction: discord.Interaction, category: str) -> None:
        await self.load_data()
        key = self._find_category_key(category)
        if key:
            items = sorted(self.data["categories"][key])
            await interaction.response.send_message(embed=self._create_embed(title=f"{key} 菜單", description="\n".join(f"- {i}" for i in items)))
        else:
            await interaction.response.send_message("找不到分類", ephemeral=True)

    @app_commands.command(name="add_food", description="新增餐點")
    @app_commands.default_permissions(manage_messages=True)
    async def slash_add_food(self, interaction: discord.Interaction, category: str, item: str) -> None:
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

    @app_commands.command(name="remove_food", description="移除餐點")
    @app_commands.default_permissions(manage_messages=True)
    async def slash_remove_food(self, interaction: discord.Interaction, category: str, item: str) -> None:
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

    @app_commands.command(name="delete_category", description="刪除分類")
    @app_commands.default_permissions(administrator=True)
    async def slash_delete_category(self, interaction: discord.Interaction, category: str) -> None:
        async with self._lock:
            await self.load_data()
            key = self._find_category_key(category)
            if key:
                del self.data["categories"][key]
                await self.save_data()
                await interaction.response.send_message(f"已刪除分類 {key}")
            else:
                await interaction.response.send_message("找不到分類", ephemeral=True)

    # --- 自動完成 ---
    async def _category_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        cl = current.lower()
        return [app_commands.Choice(name=k, value=k) for k in self.data.get("categories", {}) if cl in k.lower()][:25]

    async def _item_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        cat: Optional[str] = getattr(interaction.namespace, "category", None)
        key = self._find_category_key(cat) if cat else None
        if not key:
            return []
        cl = current.lower()
        return [app_commands.Choice(name=i, value=i) for i in self.data["categories"][key] if cl in i.lower()][:25]


async def setup(bot: commands.Bot) -> None:
    cog = Eat(bot)
    cog.slash_eat.autocomplete("category")(cog._category_autocomplete)
    cog.slash_menu.autocomplete("category")(cog._category_autocomplete)
    cog.slash_add_food.autocomplete("category")(cog._category_autocomplete)
    cog.slash_remove_food.autocomplete("category")(cog._category_autocomplete)
    cog.slash_remove_food.autocomplete("item")(cog._item_autocomplete)
    cog.slash_delete_category.autocomplete(
        "category")(cog._category_autocomplete)
    await bot.add_cog(cog)
