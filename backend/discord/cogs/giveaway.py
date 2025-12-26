"""
抽獎功能 Cog
提供抽獎建立與管理
"""

import json
import logging
import random
from datetime import datetime
from typing import Any

from config import DATA_DIR
from discord.ext import commands

import discord
from discord import app_commands, ui

logger = logging.getLogger(__name__)


class GiveawayModal(ui.Modal, title="建立抽獎"):
    """抽獎資訊輸入 Modal"""

    prize_name: Any = ui.TextInput(
        label="獎品名稱",
        placeholder="例如：Discord Nitro、Steam 遊戲序號",
        max_length=100,
    )

    prize_count: Any = ui.TextInput(
        label="獎品數量",
        placeholder="預設為 1",
        default="1",
        max_length=3,
    )

    description: Any = ui.TextInput(
        label="抽獎說明（可選）",
        placeholder="可說明參加條件、活動時間等資訊",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=300,
    )

    def __init__(self, giveaway_cog: "Giveaway"):
        super().__init__()
        self.giveaway_cog = giveaway_cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            count = int(self.prize_count.value)
            if count < 1:
                await interaction.response.send_message(
                    "獎品數量必須至少為 1", ephemeral=True
                )
                return
        except ValueError:
            await interaction.response.send_message(
                "獎品數量必須是有效的數字", ephemeral=True
            )
            return

        # 建立抽獎 embed
        embed = await self.giveaway_cog.create_giveaway_embed(
            host=interaction.user,
            prize_name=self.prize_name.value,
            prize_count=count,
            description=self.description.value or None,
        )

        # 建立按鈕 View
        view = GiveawayView(
            host_id=interaction.user.id,
            prize_name=self.prize_name.value,
            prize_count=count,
            giveaway_cog=self.giveaway_cog,
            host_avatar_url=interaction.user.display_avatar.url,
        )

        await interaction.response.send_message(embed=embed, view=view)

        # 記錄抽獎建立
        guild_name = interaction.guild.name if interaction.guild else "DM"
        logger.info(
            f"抽獎建立 | 伺服器: {guild_name} | "
            f"主持人: {interaction.user.name} | "
            f"獎品: {self.prize_name.value} x{count}"
        )


class GiveawayView(ui.View):
    """抽獎互動 Button View"""

    def __init__(
        self,
        host_id: int,
        prize_name: str,
        prize_count: int,
        giveaway_cog: "Giveaway",
        host_avatar_url: str,
    ):
        super().__init__(timeout=None)  # 不設定超時
        self.host_id = host_id
        self.prize_name = prize_name
        self.prize_count = prize_count
        self.participants: set[int] = set()
        self.giveaway_cog = giveaway_cog
        self.is_ended = False
        self.host_avatar_url = host_avatar_url

    @ui.button(label="參加抽獎", style=discord.ButtonStyle.primary)
    async def join_button(self, interaction: discord.Interaction, button: ui.Button):
        if self.is_ended:
            await interaction.response.send_message(
                self.giveaway_cog.config["messages"]["giveaway_ended"], ephemeral=True
            )
            return

        user_id = interaction.user.id

        # 切換參加狀態
        if user_id in self.participants:
            # 取消參加
            self.participants.remove(user_id)
            message = "已取消參加此抽獎"
        else:
            # 參加抽獎
            self.participants.add(user_id)
            message = f"{self.giveaway_cog.config['messages']['joined_success']}\n提示：再次點擊按鈕可取消參加"

        await interaction.response.send_message(message, ephemeral=True)

        # 更新 embed 顯示參加人數
        if interaction.message:
            embed = interaction.message.embeds[0]
            # 更新參加人數欄位
            for i, field in enumerate(embed.fields):
                if field.name and "參加人數" in field.name:
                    embed.set_field_at(
                        i,
                        name="參加人數",
                        value=f"**{len(self.participants)}** 人",
                        inline=True,
                    )
                    break
            await interaction.message.edit(embed=embed, view=self)

    @ui.button(label="結束抽獎", style=discord.ButtonStyle.danger)
    async def end_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.host_id:
            await interaction.response.send_message(
                self.giveaway_cog.config["messages"]["not_host"], ephemeral=True
            )
            return

        if self.is_ended:
            await interaction.response.send_message(
                self.giveaway_cog.config["messages"]["giveaway_ended"], ephemeral=True
            )
            return

        self.is_ended = True

        # 抽獎邏輯
        if len(self.participants) == 0:
            await interaction.response.send_message(
                self.giveaway_cog.config["messages"]["no_participants"], ephemeral=True
            )
            return

        # 隨機抽取得獎者
        winner_count = min(self.prize_count, len(self.participants))
        winner_ids = random.sample(list(self.participants), winner_count)

        # 建立結果 embed
        result_embed = await self.giveaway_cog.create_result_embed(
            host=interaction.guild.get_member(self.host_id) if interaction.guild else None,
            prize_name=self.prize_name,
            prize_count=self.prize_count,
            winner_ids=winner_ids,
            total_participants=len(self.participants),
            host_avatar_url=self.host_avatar_url,
        )

        # 禁用所有按鈕
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True

        # 將原始訊息直接編輯為結果 embed
        if interaction.message:
            await interaction.message.edit(embed=result_embed, view=self)

        # 發送得獎者通知訊息（會觸發 @mention 通知）
        winners_mention = " ".join([f"<@{user_id}>" for user_id in winner_ids])
        await interaction.response.send_message(
            f"恭喜得獎者：{winners_mention}\n請查看上方抽獎結果！"
        )

        # 記錄抽獎結束
        guild_name = interaction.guild.name if interaction.guild else "DM"
        logger.info(
            f"抽獎結束 | 伺服器: {guild_name} | "
            f"獎品: {self.prize_name} | "
            f"參加人數: {len(self.participants)} | 得獎人數: {len(winner_ids)}"
        )


class Giveaway(commands.Cog):
    """抽獎功能指令"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._load_data()

    def _load_data(self):
        """載入抽獎和全域 Embed 數據"""
        with open(DATA_DIR / "giveaway.json", "r", encoding="utf-8") as f:
            self.config = json.load(f)

        with open(DATA_DIR / "embed.json", "r", encoding="utf-8") as f:
            self.global_embed_config = json.load(f)

    async def create_giveaway_embed(
        self,
        host: discord.User | discord.Member,
        prize_name: str,
        prize_count: int,
        description: str | None = None,
    ) -> discord.Embed:
        """建立抽獎 Embed"""
        # 建立更清楚的描述
        desc_text = description if description else "點擊下方按鈕參加抽獎"

        embed = discord.Embed(
            title="【抽獎】",
            description=desc_text,
            color=discord.Color.from_str(self.config["colors"]["active"]),
            timestamp=datetime.now(),
        )

        # 設定 author - 優先使用 giveaway 專屬設定，否則使用全域設定
        giveaway_author = self.config["embed"].get("author", {})
        global_author = self.global_embed_config.get("author", {})

        author_name = giveaway_author.get("name") or global_author.get("name")
        if author_name:
            author_icon = (
                giveaway_author.get("icon_url")
                or global_author.get("icon_url")
                or None
            )
            author_url = giveaway_author.get(
                "url") or global_author.get("url") or None
            embed.set_author(
                name=author_name,
                icon_url=author_icon,
                url=author_url,
            )

        # 設定 thumbnail - 使用發起人的頭像
        embed.set_thumbnail(url=host.display_avatar.url)

        # 設定 image（用於展開 embed 寬度）- 從 JSON 取用預設圖片
        image_url = self.config["embed"].get("image")
        if image_url:
            embed.set_image(url=image_url)

        # 抽獎資訊 - 使用更清楚的格式
        embed.add_field(name="獎品", value=prize_name, inline=True)
        embed.add_field(name="數量", value=f"**{prize_count}** 個", inline=True)
        embed.add_field(name="主持人", value=host.mention, inline=False)
        embed.add_field(name="參加人數", value="**0** 人", inline=False)

        # 設定 footer - 優先使用 giveaway 專屬設定，否則使用全域設定
        giveaway_footer = self.config["embed"].get("footer", {})
        global_footer = self.global_embed_config.get("footer", {})

        footer_text = giveaway_footer.get("text") or global_footer.get("text")
        if footer_text:
            footer_icon = (
                giveaway_footer.get("icon_url")
                or global_footer.get("icon_url")
                or None
            )
            embed.set_footer(text=footer_text, icon_url=footer_icon)

        return embed

    async def create_result_embed(
        self,
        host: discord.Member | None,
        prize_name: str,
        prize_count: int,
        winner_ids: list[int],
        total_participants: int,
        host_avatar_url: str,
    ) -> discord.Embed:
        """建立開獎結果 Embed"""
        # 計算中獎率
        win_rate = (len(winner_ids) / total_participants *
                    100) if total_participants > 0 else 0

        embed = discord.Embed(
            title="【抽獎】",
            description=f"恭喜以下 **{len(winner_ids)}** 位得獎者！",
            color=discord.Color.from_str(self.config["colors"]["ended"]),
            timestamp=datetime.now(),
        )

        # 設定 author - 優先使用 giveaway 專屬設定，否則使用全域設定
        giveaway_author = self.config["embed"].get("author", {})
        global_author = self.global_embed_config.get("author", {})

        author_name = giveaway_author.get("name") or global_author.get("name")
        if author_name:
            author_icon = (
                giveaway_author.get("icon_url")
                or global_author.get("icon_url")
                or None
            )
            author_url = giveaway_author.get(
                "url") or global_author.get("url") or None
            embed.set_author(
                name=author_name,
                icon_url=author_icon,
                url=author_url,
            )

        # 設定 thumbnail - 使用發起人的頭像（保持與建立時相同）
        embed.set_thumbnail(url=host_avatar_url)

        # 設定 image（用於展開 embed 寬度）- 從 JSON 取用預設圖片
        image_url = self.config["embed"].get("image")
        if image_url:
            embed.set_image(url=image_url)

        # 獎品資訊
        embed.add_field(name="獎品", value=prize_name, inline=True)
        embed.add_field(name="數量", value=f"**{prize_count}** 個", inline=True)
        if host:
            embed.add_field(name="主持人", value=host.mention, inline=False)

        # 得獎者列表 - 使用編號顯示
        winners_list = []
        for idx, user_id in enumerate(winner_ids, 1):
            winners_list.append(f"{idx}. <@{user_id}>")
        winners_mention = "\n".join(winners_list)
        embed.add_field(name="得獎名單", value=winners_mention, inline=False)

        # 統計資訊 - 放在最底下
        embed.add_field(
            name="總參加人數", value=f"**{total_participants}** 人", inline=True)
        embed.add_field(name="中獎率", value=f"**{win_rate:.1f}%**", inline=True)

        # 設定 footer
        giveaway_footer = self.config["embed"].get("footer", {})
        global_footer = self.global_embed_config.get("footer", {})

        footer_text = giveaway_footer.get("text") or global_footer.get("text")
        if footer_text:
            footer_icon = (
                giveaway_footer.get("icon_url")
                or global_footer.get("icon_url")
                or None
            )
            embed.set_footer(text=footer_text, icon_url=footer_icon)

        return embed

    @app_commands.command(name="giveaway", description="建立抽獎活動")
    async def giveaway(self, interaction: discord.Interaction):
        """建立抽獎活動"""
        await interaction.response.send_modal(GiveawayModal(self))


async def setup(bot: commands.Bot):
    """載入 Cog"""
    await bot.add_cog(Giveaway(bot))
