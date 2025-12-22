"""
餐點推薦功能 Cog
提供智能餐點推薦與管理
"""

import asyncio
import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from discord.ext import commands

import discord
from discord import app_commands, ui

logger = logging.getLogger(__name__)


class CategoryButtonsView(ui.View):
    """分類選擇按鈕視圖"""

    def __init__(self, cog, user: discord.User):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user
        self._add_category_buttons()

    def _add_category_buttons(self):
        """動態添加分類按鈕（最多25個）"""
        categories = list(self.cog.data["categories"].keys())[:25]
        for category in categories:
            button = ui.Button(
                label=category,
                style=discord.ButtonStyle.primary,
                custom_id=f"cat_{category}"
            )
            button.callback = self._create_callback(category)
            self.add_item(button)

    def _create_callback(self, category: str):
        """為每個按鈕創建回調函數"""
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user.id:
                await interaction.response.send_message(
                    "這不是你的選單", ephemeral=True
                )
                return

            choice = await self.cog.get_recommendation(category, str(interaction.user.id))
            if not choice:
                await interaction.response.send_message(
                    f"找不到「{category}」的資料或該分類為空", ephemeral=True
                )
                return

            embed = self._create_result_embed(category, choice)
            view = RecommendationView(self.cog, category, interaction.user)
            await interaction.response.edit_message(embed=embed, view=view)

        return callback

    def _create_result_embed(self, category: str, choice: str) -> discord.Embed:
        """創建推薦結果 Embed"""
        return self.cog._create_embed(
            title=f"{category} 推薦",
            description=f"**{choice}**"
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """檢查互動權限"""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "這不是你的選單", ephemeral=True
            )
            return False
        return True


class RecommendationView(ui.View):
    """推薦結果視圖（換一個、返回）"""

    def __init__(self, cog, category: str, user: discord.User):
        super().__init__(timeout=300)
        self.cog = cog
        self.category = category
        self.user = user

    @ui.button(label="換一個", style=discord.ButtonStyle.success)
    async def reload_button(self, interaction: discord.Interaction, button: ui.Button):
        """重新推薦按鈕"""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "這不是你的選單", ephemeral=True
            )
            return

        choice = await self.cog.get_recommendation(self.category, str(interaction.user.id))
        if not choice:
            await interaction.response.send_message(
                f"找不到「{self.category}」的資料", ephemeral=True
            )
            return

        embed = self.cog._create_embed(
            title=f"{self.category} 推薦",
            description=f"**{choice}**"
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="回分類列表", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: ui.Button):
        """返回分類列表按鈕"""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "這不是你的選單", ephemeral=True
            )
            return

        # 檢查是否有時段推薦（與主指令一致）
        time_category = self.cog._get_time_based_category()
        time_hint = ""
        if time_category and time_category in self.cog.data["categories"]:
            time_hint = f"\n\n目前時段推薦：{time_category}"

        embed = self.cog._create_embed(
            title="請選擇餐點分類",
            description=f"點選下方按鈕以獲得該分類的推薦餐點{time_hint}"
        )
        view = CategoryButtonsView(self.cog, interaction.user)
        await interaction.response.edit_message(embed=embed, view=view)


class Eat(commands.Cog):
    """餐點推薦功能"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 路徑：/app/cogs/eat.py -> /app/data/eat.json
        base_dir = Path(__file__).parent.parent  # /app
        self.data_file = base_dir / "data" / "eat.json"
        self.global_embed_file = base_dir / "data" / "embed.json"
        self.data: dict[str, Any] = {}
        self.global_embed_config: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._dirty = False
        logger.info("Eat cog 初始化完成")

    async def cog_load(self):
        """Cog 載入時執行"""
        await self.load_data()
        await self.load_global_embed()

    async def load_data(self):
        """載入數據"""
        try:
            async with self._lock:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    self.data = json.load(f)

                # 確保必要的鍵存在
                if "categories" not in self.data:
                    self.data["categories"] = {}
                if "recent" not in self.data:
                    self.data["recent"] = {}
                if "settings" not in self.data:
                    self.data["settings"] = {
                        "anti_repeat": {"enabled": True, "size": 5},
                        "time_based": {"enabled": True, "mapping": {}}
                    }

                category_count = len(self.data["categories"])
                item_count = sum(len(items) for items in self.data["categories"].values())
                logger.info(f"載入了 {category_count} 個分類，共 {item_count} 個項目")
        except FileNotFoundError:
            logger.error(f"找不到數據文件：{self.data_file}")
            self.data = {
                "categories": {},
                "recent": {},
                "settings": {
                    "anti_repeat": {"enabled": True, "size": 5},
                    "time_based": {"enabled": True, "mapping": {}}
                }
            }
        except Exception as e:
            logger.error(f"載入數據失敗：{e}")
            self.data = {
                "categories": {},
                "recent": {},
                "settings": {
                    "anti_repeat": {"enabled": True, "size": 5},
                    "time_based": {"enabled": True, "mapping": {}}
                }
            }

    async def save_data(self):
        """保存數據"""
        try:
            async with self._lock:
                with open(self.data_file, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
                self._dirty = False
                logger.info("數據已保存")
        except Exception as e:
            logger.error(f"保存數據失敗：{e}")

    async def load_global_embed(self):
        """載入全域 Embed 配置"""
        try:
            with open(self.global_embed_file, "r", encoding="utf-8") as f:
                self.global_embed_config = json.load(f)
        except FileNotFoundError:
            logger.warning(f"找不到全域 Embed 配置文件：{self.global_embed_file}")
            self.global_embed_config = {}
        except Exception as e:
            logger.error(f"載入全域 Embed 配置失敗：{e}")
            self.global_embed_config = {}

    def _create_embed(self, title: str, description: str = "", color: discord.Color = discord.Color.blue()) -> discord.Embed:
        """創建帶有配置的 Embed"""
        embed = discord.Embed(title=title, description=description, color=color)

        # 設定 author - 優先使用 eat 專屬設定，否則使用全域設定
        eat_author = self.data.get("embed", {}).get("author", {})
        global_author = self.global_embed_config.get("author", {})

        author_name = eat_author.get("name") or global_author.get("name")
        if author_name:
            author_icon = eat_author.get("icon_url") or global_author.get("icon_url") or None
            author_url = eat_author.get("url") or global_author.get("url") or None
            embed.set_author(name=author_name, icon_url=author_icon, url=author_url)

        # 設定 thumbnail
        thumbnail_url = self.data.get("embed", {}).get("thumbnail")
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)

        # 設定 footer - 優先使用 eat 專屬設定，否則使用全域設定
        eat_footer = self.data.get("embed", {}).get("footer", {})
        global_footer = self.global_embed_config.get("footer", {})

        footer_text = eat_footer.get("text") or global_footer.get("text")
        if footer_text:
            footer_icon = eat_footer.get("icon_url") or global_footer.get("icon_url") or None
            embed.set_footer(text=footer_text, icon_url=footer_icon)

        return embed

    def _normalize(self, text: str) -> str:
        """規範化文字（移除空格並轉小寫）"""
        return text.strip().lower().replace(" ", "")

    def _get_time_based_category(self) -> str | None:
        """根據當前時間獲取推薦分類"""
        if not self.data["settings"]["time_based"].get("enabled", False):
            return None

        now = datetime.now().strftime("%H:%M")
        mapping = self.data["settings"]["time_based"].get("mapping", {})

        for time_range, category in mapping.items():
            try:
                start, end = time_range.split("-")
                if start <= now <= end:
                    return category
            except ValueError:
                continue

        return None

    async def get_recommendation(self, category: str, user_id: str) -> str | None:
        """獲取推薦項目（帶防重複機制）"""
        async with self._lock:
            # 特殊處理：隨機套餐
            category_key = self._find_category_key(category)
            if category_key and self._normalize(category_key) == self._normalize("隨機套餐"):
                return await self._get_random_combo(user_id)

            # 獲取分類項目
            if not category_key or category_key not in self.data["categories"]:
                return None

            items = self.data["categories"][category_key]
            if not items:
                return None

            # 防重複機制
            anti_repeat = self.data["settings"]["anti_repeat"]
            if anti_repeat.get("enabled", True):
                recent_items = self.data["recent"].get(user_id, {}).get(category_key, [])
                available = [item for item in items if item not in recent_items]

                # 如果所有項目都在最近推薦中，重置
                if not available:
                    available = items
                    recent_items = []

                choice = random.choice(available)

                # 更新最近推薦記錄
                if user_id not in self.data["recent"]:
                    self.data["recent"][user_id] = {}
                if category_key not in self.data["recent"][user_id]:
                    self.data["recent"][user_id][category_key] = []

                self.data["recent"][user_id][category_key].append(choice)

                # 限制記錄大小
                max_size = anti_repeat.get("size", 5)
                if len(self.data["recent"][user_id][category_key]) > max_size:
                    self.data["recent"][user_id][category_key].pop(0)

                self._dirty = True
            else:
                choice = random.choice(items)

            return choice

    async def _get_random_combo(self, user_id: str) -> str:
        """獲取隨機套餐（食物+飲料）"""
        # 收集所有食物（排除飲料類分類）
        food_items = []
        drink_items = []

        for category, items in self.data["categories"].items():
            normalized_cat = self._normalize(category)
            if normalized_cat in [self._normalize("飲料"), self._normalize("飲料店")]:
                drink_items.extend(items)
            elif normalized_cat != self._normalize("隨機套餐"):
                food_items.extend(items)

        # 隨機選擇
        food = random.choice(food_items) if food_items else "沒有食物選項"
        drink = random.choice(drink_items) if drink_items else "水"

        return f"{food} + {drink}"

    def _find_category_key(self, category: str) -> str | None:
        """查找分類鍵（模糊匹配）"""
        normalized = self._normalize(category)
        for key in self.data["categories"].keys():
            if self._normalize(key) == normalized:
                return key
        return None

    # ==================== 斜線指令 ====================

    @app_commands.command(name="eat", description="獲得餐點推薦")
    @app_commands.describe(category="餐點分類（可選，不填會顯示選單）")
    async def slash_eat(self, interaction: discord.Interaction, category: str | None = None):
        """主要推薦指令"""
        await self.load_data()

        # 如果沒有指定分類，顯示選單
        if not category:
            if not self.data["categories"]:
                await interaction.response.send_message(
                    "目前沒有任何分類，請先新增一些內容", ephemeral=True
                )
                return

            # 檢查是否有時段推薦
            time_category = self._get_time_based_category()
            time_hint = ""
            if time_category and time_category in self.data["categories"]:
                time_hint = f"\n\n目前時段推薦：{time_category}"

            embed = self._create_embed(
                title="請選擇餐點分類",
                description=f"點選下方按鈕以獲得該分類的推薦餐點{time_hint}"
            )
            view = CategoryButtonsView(self, interaction.user)
            await interaction.response.send_message(embed=embed, view=view)
            return

        # 指定分類推薦
        choice = await self.get_recommendation(category, str(interaction.user.id))
        if not choice:
            await interaction.response.send_message(
                f"找不到「{category}」分類或該分類為空", ephemeral=True
            )
            return

        await interaction.response.send_message(f"推薦你：**{choice}**")
        if self._dirty:
            await self.save_data()

    @app_commands.command(name="categories", description="查看所有可用的餐點分類")
    async def slash_categories(self, interaction: discord.Interaction):
        """顯示所有分類"""
        await self.load_data()

        if not self.data["categories"]:
            await interaction.response.send_message(
                "目前沒有任何分類", ephemeral=True
            )
            return

        embed = self._create_embed(title="所有餐點分類")

        for category, items in self.data["categories"].items():
            embed.add_field(
                name=f"{category}",
                value=f"{len(items)} 項",
                inline=True
            )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="menu", description="查看指定分類的所有餐點選項")
    @app_commands.describe(category="要查看的餐點分類")
    async def slash_menu(self, interaction: discord.Interaction, category: str):
        """顯示分類菜單"""
        await self.load_data()

        category_key = self._find_category_key(category)
        if not category_key or category_key not in self.data["categories"]:
            await interaction.response.send_message(
                f"找不到「{category}」分類", ephemeral=True
            )
            return

        items = self.data["categories"][category_key]
        if not items:
            await interaction.response.send_message(
                f"「{category}」分類目前沒有項目", ephemeral=True
            )
            return

        embed = self._create_embed(
            title=f"{category_key} 的餐點選項",
            description="\n".join(f"- {item}" for item in sorted(items))
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="add_food", description="新增餐點到指定分類")
    @app_commands.describe(category="餐點分類", item="要新增的餐點名稱")
    @app_commands.default_permissions(manage_messages=True)
    async def slash_add_food(self, interaction: discord.Interaction, category: str, item: str):
        """新增餐點項目"""
        async with self._lock:
            await self.load_data()

            category_key = self._find_category_key(category) or category

            if category_key not in self.data["categories"]:
                self.data["categories"][category_key] = []

            # 檢查是否已存在
            normalized_items = [self._normalize(x) for x in self.data["categories"][category_key]]
            if self._normalize(item) in normalized_items:
                await interaction.response.send_message(
                    f"「{item}」已經在「{category_key}」分類中了", ephemeral=True
                )
                return

            self.data["categories"][category_key].append(item)
            await self.save_data()

            await interaction.response.send_message(
                f"已將「{item}」新增到「{category_key}」分類"
            )

    @app_commands.command(name="remove_food", description="從指定分類移除餐點")
    @app_commands.describe(category="餐點分類", item="要移除的餐點名稱")
    @app_commands.default_permissions(manage_messages=True)
    async def slash_remove_food(self, interaction: discord.Interaction, category: str, item: str):
        """移除餐點項目"""
        async with self._lock:
            await self.load_data()

            category_key = self._find_category_key(category)
            if not category_key or category_key not in self.data["categories"]:
                await interaction.response.send_message(
                    f"找不到「{category}」分類", ephemeral=True
                )
                return

            # 查找並移除項目
            normalized_item = self._normalize(item)
            for idx, existing_item in enumerate(self.data["categories"][category_key]):
                if self._normalize(existing_item) == normalized_item:
                    removed = self.data["categories"][category_key].pop(idx)

                    # 如果分類變空，刪除分類
                    if not self.data["categories"][category_key]:
                        del self.data["categories"][category_key]

                    await self.save_data()
                    await interaction.response.send_message(
                        f"已從「{category_key}」分類中移除「{removed}」"
                    )
                    return

            await interaction.response.send_message(
                f"在「{category_key}」分類中找不到「{item}」", ephemeral=True
            )

    @app_commands.command(name="delete_category", description="刪除整個餐點分類")
    @app_commands.describe(category="要刪除的餐點分類")
    @app_commands.default_permissions(administrator=True)
    async def slash_delete_category(self, interaction: discord.Interaction, category: str):
        """刪除分類"""
        async with self._lock:
            await self.load_data()

            category_key = self._find_category_key(category)
            if not category_key or category_key not in self.data["categories"]:
                await interaction.response.send_message(
                    f"找不到「{category}」分類", ephemeral=True
                )
                return

            del self.data["categories"][category_key]
            await self.save_data()

            await interaction.response.send_message(
                f"已刪除分類「{category_key}」"
            )

    # ==================== 自動完成 ====================

    async def _category_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """分類自動完成"""
        await self.load_data()
        choices = []
        current_lower = current.lower()

        for category_key in self.data["categories"].keys():
            if current_lower in category_key.lower():
                choices.append(app_commands.Choice(name=category_key, value=category_key))
                if len(choices) >= 25:
                    break

        return choices

    async def _item_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """項目自動完成"""
        category = getattr(interaction.namespace, "category", None)
        if not category:
            return []

        await self.load_data()
        category_key = self._find_category_key(category)
        if not category_key or category_key not in self.data["categories"]:
            return []

        choices = []
        current_lower = current.lower()

        for item in self.data["categories"][category_key]:
            if current_lower in item.lower():
                choices.append(app_commands.Choice(name=item, value=item))
                if len(choices) >= 25:
                    break

        return choices


async def setup(bot: commands.Bot):
    """載入 Cog"""
    cog = Eat(bot)

    # 設置自動完成
    cog.slash_eat.autocomplete("category")(cog._category_autocomplete)
    cog.slash_menu.autocomplete("category")(cog._category_autocomplete)
    cog.slash_add_food.autocomplete("category")(cog._category_autocomplete)
    cog.slash_remove_food.autocomplete("category")(cog._category_autocomplete)
    cog.slash_remove_food.autocomplete("item")(cog._item_autocomplete)
    cog.slash_delete_category.autocomplete("category")(cog._category_autocomplete)

    await bot.add_cog(cog)
