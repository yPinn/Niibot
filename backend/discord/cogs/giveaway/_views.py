"""Discord UI views and modals for the giveaway system."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import discord
from discord import ui

if TYPE_CHECKING:
    from .cog import GiveawayCog

from ._embeds import create_result_embed

LOGGER = logging.getLogger(__name__)


class TimeSelectView(ui.View):
    """時間選擇視圖"""

    def __init__(self, giveaway_cog: GiveawayCog):
        super().__init__(timeout=60)
        self.giveaway_cog = giveaway_cog

    @ui.select(
        placeholder="選擇抽獎持續時間",
        options=[
            discord.SelectOption(label="1 小時", value="1h"),
            discord.SelectOption(label="6 小時", value="6h"),
            discord.SelectOption(label="1 天", value="1d"),
            discord.SelectOption(label="3 天", value="3d"),
            discord.SelectOption(label="7 天", value="7d"),
            discord.SelectOption(label="手動結束", value="manual"),
        ],
    )
    async def time_select(self, interaction: discord.Interaction, select: ui.Select[Any]) -> None:
        value = select.values[0]

        end_time = None
        if value != "manual":
            if value.endswith("h"):
                end_time = datetime.now(UTC) + timedelta(hours=int(value[:-1]))
            elif value.endswith("d"):
                end_time = datetime.now(UTC) + timedelta(days=int(value[:-1]))

        await interaction.response.send_modal(GiveawayModal(self.giveaway_cog, end_time))


class GiveawayModal(ui.Modal, title="建立抽獎"):
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

    def __init__(self, giveaway_cog: GiveawayCog, end_time: datetime | None = None):
        super().__init__()
        self.giveaway_cog = giveaway_cog
        self.end_time = end_time

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            count = int(self.prize_count.value)
            if count < 1:
                await interaction.response.send_message("獎品數量必須至少為 1", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("獎品數量必須是有效的數字", ephemeral=True)
            return

        embed = await self.giveaway_cog.create_giveaway_embed(
            host=interaction.user,
            prize_name=self.prize_name.value,
            prize_count=count,
            description=self.description.value or None,
            end_time=self.end_time,
        )

        view = GiveawayView(
            host_id=interaction.user.id,
            prize_name=self.prize_name.value,
            prize_count=count,
            giveaway_cog=self.giveaway_cog,
            host_avatar_url=interaction.user.display_avatar.url,
            end_time=self.end_time,
        )

        await interaction.response.send_message(embed=embed, view=view)
        message = await interaction.original_response()

        if self.end_time:
            await self.giveaway_cog.save_active_giveaway(
                message_id=message.id,
                channel_id=message.channel.id,
                guild_id=interaction.guild.id if interaction.guild else None,
                host_id=interaction.user.id,
                prize_name=self.prize_name.value,
                prize_count=count,
                end_time=self.end_time.isoformat(),
                host_avatar_url=interaction.user.display_avatar.url,
            )

        guild_name = interaction.guild.name if interaction.guild else "DM"
        duration_str = self.end_time.strftime("%Y-%m-%d %H:%M") if self.end_time else "手動結束"
        LOGGER.info(
            f"Giveaway created | Guild: {guild_name} | "
            f"Host: {interaction.user.name} | "
            f"Prize: {self.prize_name.value} x{count} | "
            f"End time: {duration_str}"
        )


class ConfirmCancelView(ui.View):
    """取消抽獎確認視圖"""

    def __init__(self) -> None:
        super().__init__(timeout=30)
        self.value: bool | None = None

    @ui.button(label="確認取消", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button[Any]) -> None:
        self.value = True
        self.stop()
        await interaction.response.edit_message(content="已取消抽獎", view=None)

    @ui.button(label="返回", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button[Any]) -> None:
        self.value = False
        self.stop()
        await interaction.response.edit_message(content="已取消操作", view=None)


class GiveawayView(ui.View):
    def __init__(
        self,
        host_id: int,
        prize_name: str,
        prize_count: int,
        giveaway_cog: GiveawayCog,
        host_avatar_url: str,
        end_time: datetime | None = None,
    ):
        timeout_seconds = None
        if end_time:
            remaining = (end_time - datetime.now(UTC)).total_seconds()
            timeout_seconds = min(remaining, 900) if remaining > 0 else 1

        super().__init__(timeout=timeout_seconds)
        self.host_id = host_id
        self.prize_name = prize_name
        self.prize_count = prize_count
        self.participants: set[int] = set()
        self.giveaway_cog = giveaway_cog
        self.is_ended = False
        self.host_avatar_url = host_avatar_url
        self.end_time = end_time
        self._lock = asyncio.Lock()

    async def on_timeout(self) -> None:
        pass

    @ui.button(label="參加抽獎", style=discord.ButtonStyle.primary, custom_id="giveaway:join")
    async def join_button(self, interaction: discord.Interaction, button: ui.Button[Any]) -> None:
        if self.end_time and datetime.now(UTC) >= self.end_time:
            await interaction.response.send_message("此抽獎已截止，無法再參加", ephemeral=True)
            return

        if self.is_ended:
            await interaction.response.send_message(
                self.giveaway_cog.config["messages"]["giveaway_ended"], ephemeral=True
            )
            return

        async with self._lock:
            user_id = interaction.user.id

            if user_id in self.participants:
                self.participants.remove(user_id)
                message = "已取消參加此抽獎"
            else:
                self.participants.add(user_id)
                message = f"{self.giveaway_cog.config['messages']['joined_success']}\n提示：再次點擊按鈕可取消參加"

            if interaction.message:
                await self.giveaway_cog.update_participants(
                    interaction.message.id, list(self.participants)
                )

        await interaction.response.send_message(message, ephemeral=True)

        if interaction.message:
            embed = interaction.message.embeds[0]
            for i, field in enumerate(embed.fields):
                if field.name and "參加人數" in field.name:
                    embed.set_field_at(
                        i, name="參加人數", value=f"**{len(self.participants)}** 人", inline=True
                    )
                    break
            await interaction.message.edit(embed=embed, view=self)

    @ui.button(label="結束抽獎", style=discord.ButtonStyle.danger, custom_id="giveaway:end")
    async def end_button(self, interaction: discord.Interaction, button: ui.Button[Any]) -> None:
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

        await self._end_giveaway(interaction)

    @ui.button(label="取消抽獎", style=discord.ButtonStyle.secondary, custom_id="giveaway:cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button[Any]) -> None:
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

        confirm_view = ConfirmCancelView()
        await interaction.response.send_message(
            f"確定要取消此抽獎嗎？\n獎品：{self.prize_name}\n目前參加人數：{len(self.participants)} 人\n\n此操作無法復原。",
            view=confirm_view,
            ephemeral=True,
        )

        await confirm_view.wait()
        if confirm_view.value:
            await self._cancel_giveaway(interaction)

    async def _cancel_giveaway(self, interaction: discord.Interaction) -> None:
        self.is_ended = True

        cancel_embed = self.giveaway_cog._embed.build(
            title="【抽獎已取消】",
            description="此抽獎已被主持人取消",
            color=discord.Color.red(),
            timestamp=datetime.now(UTC),
        )
        cancel_embed.add_field(name="獎品", value=self.prize_name, inline=True)
        cancel_embed.add_field(name="數量", value=f"**{self.prize_count}** 個", inline=True)
        cancel_embed.add_field(
            name="參加人數", value=f"**{len(self.participants)}** 人", inline=False
        )

        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True

        original_message = interaction.message
        if original_message:
            await original_message.edit(embed=cancel_embed, view=self)
            await self.giveaway_cog.remove_active_giveaway(original_message.id)

        guild_name = interaction.guild.name if interaction.guild else "DM"
        LOGGER.info(
            f"Giveaway cancelled | Guild: {guild_name} | "
            f"Prize: {self.prize_name} | Participants: {len(self.participants)}"
        )

    async def _end_giveaway(self, interaction: discord.Interaction) -> None:
        self.is_ended = True

        if len(self.participants) == 0:
            await interaction.response.send_message(
                self.giveaway_cog.config["messages"]["no_participants"], ephemeral=True
            )
            for item in self.children:
                if isinstance(item, ui.Button):
                    item.disabled = True
            if interaction.message:
                await interaction.message.edit(view=self)
            return

        winner_count = min(self.prize_count, len(self.participants))
        winner_ids = random.sample(list(self.participants), winner_count)

        result_embed = create_result_embed(
            config=self.giveaway_cog.config,
            global_config=self.giveaway_cog.global_embed_config,
            host=interaction.guild.get_member(self.host_id) if interaction.guild else None,
            prize_name=self.prize_name,
            prize_count=self.prize_count,
            winner_ids=winner_ids,
            total_participants=len(self.participants),
            host_avatar_url=self.host_avatar_url,
        )

        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True

        if interaction.message:
            await interaction.message.edit(embed=result_embed, view=self)

        winners_mention = " ".join([f"<@{uid}>" for uid in winner_ids])
        await interaction.response.send_message(
            f"恭喜得獎者：{winners_mention}\n請查看上方抽獎結果！"
        )

        if interaction.message:
            await self.giveaway_cog.remove_active_giveaway(interaction.message.id)

        guild_name = interaction.guild.name if interaction.guild else "DM"
        LOGGER.info(
            f"Giveaway ended | Guild: {guild_name} | "
            f"Prize: {self.prize_name} | "
            f"Participants: {len(self.participants)} | Winners: {len(winner_ids)}"
        )
