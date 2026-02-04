"""Giveaway management commands"""

import json
import logging
import random
from datetime import datetime, timedelta
from typing import Any

import discord
from discord import app_commands, ui
from discord.ext import commands, tasks

from config import DATA_DIR

logger = logging.getLogger(__name__)


class TimeSelectView(ui.View):
    """時間選擇視圖"""

    def __init__(self, giveaway_cog: "Giveaway"):
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
                hours = int(value[:-1])
                end_time = datetime.now() + timedelta(hours=hours)
            elif value.endswith("d"):
                days = int(value[:-1])
                end_time = datetime.now() + timedelta(days=days)

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

    def __init__(self, giveaway_cog: "Giveaway", end_time: datetime | None = None):
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
        logger.info(
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
        giveaway_cog: "Giveaway",
        host_avatar_url: str,
        end_time: datetime | None = None,
    ):
        # 如果有截止時間，計算 timeout；否則設為 None
        timeout_seconds = None
        if end_time:
            remaining = (end_time - datetime.now()).total_seconds()
            # discord.py 的 timeout 最大值約為 15 分鐘，超過則設為 None
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

    async def on_timeout(self) -> None:
        """View timeout 時觸發（僅在有截止時間時）"""
        # 這個只會在 15 分鐘內的抽獎觸發
        # 長時間的抽獎由背景任務處理
        pass

    @ui.button(label="參加抽獎", style=discord.ButtonStyle.primary, custom_id="giveaway:join")
    async def join_button(self, interaction: discord.Interaction, button: ui.Button[Any]) -> None:
        # 檢查是否已截止
        if self.end_time and datetime.now() >= self.end_time:
            await interaction.response.send_message("此抽獎已截止，無法再參加", ephemeral=True)
            return

        if self.is_ended:
            await interaction.response.send_message(
                self.giveaway_cog.config["messages"]["giveaway_ended"], ephemeral=True
            )
            return

        user_id = interaction.user.id

        if user_id in self.participants:
            self.participants.remove(user_id)
            message = "已取消參加此抽獎"
        else:
            self.participants.add(user_id)
            message = f"{self.giveaway_cog.config['messages']['joined_success']}\n提示：再次點擊按鈕可取消參加"

        # 同步參加者到持久化存儲
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
                        i,
                        name="參加人數",
                        value=f"**{len(self.participants)}** 人",
                        inline=True,
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

        # 顯示確認對話框
        confirm_view = ConfirmCancelView()
        await interaction.response.send_message(
            f"確定要取消此抽獎嗎？\n獎品：{self.prize_name}\n目前參加人數：{len(self.participants)} 人\n\n此操作無法復原。",
            view=confirm_view,
            ephemeral=True,
        )

        # 等待用戶確認
        await confirm_view.wait()

        if confirm_view.value:
            # 用戶確認取消
            await self._cancel_giveaway(interaction)

    async def _cancel_giveaway(self, interaction: discord.Interaction) -> None:
        """取消抽獎的邏輯"""
        self.is_ended = True

        # 創建取消通知 embed
        cancel_embed = discord.Embed(
            title="【抽獎已取消】",
            description="此抽獎已被主持人取消",
            color=discord.Color.red(),
            timestamp=datetime.now(),
        )

        cancel_embed.add_field(name="獎品", value=self.prize_name, inline=True)
        cancel_embed.add_field(name="數量", value=f"**{self.prize_count}** 個", inline=True)
        cancel_embed.add_field(
            name="參加人數", value=f"**{len(self.participants)}** 人", inline=False
        )

        # 禁用所有按鈕
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True

        # 取得原始訊息
        original_message = interaction.message
        if original_message:
            # 編輯原始抽獎訊息
            await original_message.edit(embed=cancel_embed, view=self)

            # 從活動抽獎中移除
            await self.giveaway_cog.remove_active_giveaway(original_message.id)

        guild_name = interaction.guild.name if interaction.guild else "DM"
        logger.info(
            f"Giveaway cancelled | Guild: {guild_name} | "
            f"Prize: {self.prize_name} | "
            f"Participants: {len(self.participants)}"
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

        result_embed = await self.giveaway_cog.create_result_embed(
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

        winners_mention = " ".join([f"<@{user_id}>" for user_id in winner_ids])
        await interaction.response.send_message(
            f"恭喜得獎者：{winners_mention}\n請查看上方抽獎結果！"
        )

        if interaction.message:
            await self.giveaway_cog.remove_active_giveaway(interaction.message.id)

        guild_name = interaction.guild.name if interaction.guild else "DM"
        logger.info(
            f"Giveaway ended | Guild: {guild_name} | "
            f"Prize: {self.prize_name} | "
            f"Participants: {len(self.participants)} | Winners: {len(winner_ids)}"
        )


class Giveaway(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._load_data()
        self.active_giveaways_file = DATA_DIR / "active_giveaways.json"
        self.active_giveaways: dict[int, dict] = {}
        self._load_active_giveaways()

    async def cog_load(self) -> None:
        """Cog 載入時啟動背景任務"""
        self.check_giveaway_expiry.start()
        logger.info("Giveaway expiry checker started")

    async def cog_unload(self) -> None:
        """Cog 卸載時停止背景任務"""
        self.check_giveaway_expiry.cancel()
        logger.info("Giveaway expiry checker stopped")

    def _load_data(self) -> None:
        with open(DATA_DIR / "giveaway.json", encoding="utf-8") as f:
            self.config = json.load(f)
        with open(DATA_DIR / "embed.json", encoding="utf-8") as f:
            self.global_embed_config = json.load(f)

    def _load_active_giveaways(self) -> None:
        """載入活動中的抽獎"""
        if self.active_giveaways_file.exists():
            try:
                with open(self.active_giveaways_file, encoding="utf-8") as f:
                    self.active_giveaways = json.load(f)
                    # 轉換 key 為 int
                    self.active_giveaways = {int(k): v for k, v in self.active_giveaways.items()}
                logger.info(f"Loaded {len(self.active_giveaways)} active giveaways")
            except Exception as e:
                logger.error(f"Failed to load active giveaways: {e}")
                self.active_giveaways = {}
        else:
            self.active_giveaways = {}

    def _save_active_giveaways(self) -> None:
        """儲存活動中的抽獎"""
        try:
            with open(self.active_giveaways_file, "w", encoding="utf-8") as f:
                json.dump(self.active_giveaways, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save active giveaways: {e}")

    async def save_active_giveaway(
        self,
        message_id: int,
        channel_id: int,
        guild_id: int | None,
        host_id: int,
        prize_name: str,
        prize_count: int,
        end_time: str,
        host_avatar_url: str,
    ) -> None:
        """儲存一個活動中的抽獎"""
        self.active_giveaways[message_id] = {
            "channel_id": channel_id,
            "guild_id": guild_id,
            "host_id": host_id,
            "prize_name": prize_name,
            "prize_count": prize_count,
            "end_time": end_time,
            "host_avatar_url": host_avatar_url,
            "participants": [],
        }
        self._save_active_giveaways()

    async def remove_active_giveaway(self, message_id: int) -> None:
        """移除一個活動中的抽獎"""
        if message_id in self.active_giveaways:
            del self.active_giveaways[message_id]
            self._save_active_giveaways()

    async def update_participants(self, message_id: int, participants: list[int]) -> None:
        """更新抽獎的參加者列表"""
        if message_id in self.active_giveaways:
            self.active_giveaways[message_id]["participants"] = participants
            self._save_active_giveaways()

    @tasks.loop(minutes=1)
    async def check_giveaway_expiry(self) -> None:
        """每分鐘檢查是否有抽獎到期"""
        now = datetime.now()
        expired = []

        for message_id, data in self.active_giveaways.items():
            end_time = datetime.fromisoformat(data["end_time"])
            if now >= end_time:
                expired.append((message_id, data))

        for message_id, data in expired:
            try:
                await self._auto_end_giveaway(message_id, data)
            except Exception as e:
                logger.error(f"Failed to auto-end giveaway {message_id}: {e}")

    @check_giveaway_expiry.before_loop
    async def before_check_giveaway_expiry(self) -> None:
        """等待 bot 準備就緒"""
        await self.bot.wait_until_ready()

    async def _auto_end_giveaway(self, message_id: int, data: dict[str, Any]) -> None:
        """自動結束到期的抽獎"""
        try:
            channel = self.bot.get_channel(data["channel_id"])
            if not channel:
                logger.warning(f"Channel {data['channel_id']} not found for giveaway {message_id}")
                await self.remove_active_giveaway(message_id)
                return

            # 類型檢查：確保 channel 支援 fetch_message
            if not hasattr(channel, "fetch_message"):
                logger.warning(f"Channel {channel} does not support fetch_message")
                await self.remove_active_giveaway(message_id)
                return

            message = await channel.fetch_message(message_id)  # type: ignore[union-attr]
            if not message:
                logger.warning(f"Message {message_id} not found")
                await self.remove_active_giveaway(message_id)
                return

            # 取得參加者列表
            participants = data.get("participants", [])
            participant_count = len(participants)

            guild = self.bot.get_guild(data["guild_id"]) if data["guild_id"] else None
            host = guild.get_member(data["host_id"]) if guild else None

            view = ui.View()
            for component in message.components:
                if hasattr(component, "children"):
                    for item in component.children:
                        if isinstance(item, discord.Button):
                            button: ui.Button = ui.Button(
                                label=item.label,
                                style=item.style,
                                disabled=True,
                                custom_id=item.custom_id,
                            )
                            view.add_item(button)

            if participant_count == 0:
                no_participant_embed = discord.Embed(
                    title="【抽獎已截止】",
                    description="此抽獎已截止，但沒有人參加",
                    color=discord.Color.orange(),
                    timestamp=datetime.now(),
                )

                no_participant_embed.add_field(name="獎品", value=data["prize_name"], inline=True)
                no_participant_embed.add_field(
                    name="數量", value=f"**{data['prize_count']}** 個", inline=True
                )
                if host:
                    no_participant_embed.add_field(name="主持人", value=host.mention, inline=False)
                no_participant_embed.add_field(name="參加人數", value="**0** 人", inline=False)

                await message.edit(embed=no_participant_embed, view=view)
                await self.remove_active_giveaway(message_id)

                logger.info(
                    f"Auto-ended giveaway {message_id} | "
                    f"Prize: {data['prize_name']} | No participants"
                )
                return

            winner_count = min(data["prize_count"], participant_count)
            winner_ids = random.sample(participants, winner_count)

            result_embed = await self.create_result_embed(
                host=host,
                prize_name=data["prize_name"],
                prize_count=data["prize_count"],
                winner_ids=winner_ids,
                total_participants=participant_count,
                host_avatar_url=data["host_avatar_url"],
            )

            await message.edit(embed=result_embed, view=view)

            winners_mention = " ".join([f"<@{user_id}>" for user_id in winner_ids])
            if hasattr(channel, "send"):
                await channel.send(
                    f"【抽獎結束】恭喜得獎者：{winners_mention}\n請查看上方抽獎結果！"
                )

            await self.remove_active_giveaway(message_id)
            logger.info(
                f"Auto-ended giveaway {message_id} | "
                f"Prize: {data['prize_name']} | "
                f"Participants: {participant_count} | Winners: {winner_count}"
            )

        except discord.NotFound:
            logger.warning(f"Message {message_id} not found, removing from active giveaways")
            await self.remove_active_giveaway(message_id)
        except Exception as e:
            logger.error(f"Error auto-ending giveaway {message_id}: {e}", exc_info=e)

    async def create_giveaway_embed(
        self,
        host: discord.User | discord.Member,
        prize_name: str,
        prize_count: int,
        description: str | None = None,
        end_time: datetime | None = None,
    ) -> discord.Embed:
        desc_text = description if description else "點擊下方按鈕參加抽獎"

        embed = discord.Embed(
            title="【抽獎】",
            description=desc_text,
            color=discord.Color.from_str(self.config["colors"]["active"]),
            timestamp=datetime.now(),
        )

        giveaway_author = self.config["embed"].get("author", {})
        global_author = self.global_embed_config.get("author", {})

        author_name = giveaway_author.get("name") or global_author.get("name")
        if author_name:
            author_icon = giveaway_author.get("icon_url") or global_author.get("icon_url") or None
            author_url = giveaway_author.get("url") or global_author.get("url") or None
            embed.set_author(
                name=author_name,
                icon_url=author_icon,
                url=author_url,
            )

        embed.set_thumbnail(url=host.display_avatar.url)

        image_url = self.config["embed"].get("image")
        if image_url:
            embed.set_image(url=image_url)

        embed.add_field(name="獎品", value=prize_name, inline=True)
        embed.add_field(name="數量", value=f"**{prize_count}** 個", inline=True)
        embed.add_field(name="主持人", value=host.mention, inline=False)

        if end_time:
            time_str = end_time.strftime("%m/%d %H:%M")
            timestamp_unix = int(end_time.timestamp())
            time_info = f"**{time_str}**   (<t:{timestamp_unix}:R>)"
            embed.add_field(name="截止時間", value=time_info, inline=False)

        embed.add_field(name="參加人數", value="**0** 人", inline=False)

        giveaway_footer = self.config["embed"].get("footer", {})
        global_footer = self.global_embed_config.get("footer", {})

        footer_text = giveaway_footer.get("text") or global_footer.get("text")
        if footer_text:
            footer_icon = giveaway_footer.get("icon_url") or global_footer.get("icon_url") or None
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
        win_rate = (len(winner_ids) / total_participants * 100) if total_participants > 0 else 0

        embed = discord.Embed(
            title="【抽獎結果】",
            description=f"恭喜以下 **{len(winner_ids)}** 位得獎者！",
            color=discord.Color.from_str(self.config["colors"]["ended"]),
            timestamp=datetime.now(),
        )

        giveaway_author = self.config["embed"].get("author", {})
        global_author = self.global_embed_config.get("author", {})

        author_name = giveaway_author.get("name") or global_author.get("name")
        if author_name:
            author_icon = giveaway_author.get("icon_url") or global_author.get("icon_url") or None
            author_url = giveaway_author.get("url") or global_author.get("url") or None
            embed.set_author(
                name=author_name,
                icon_url=author_icon,
                url=author_url,
            )

        embed.set_thumbnail(url=host_avatar_url)

        image_url = self.config["embed"].get("image")
        if image_url:
            embed.set_image(url=image_url)

        embed.add_field(name="獎品", value=prize_name, inline=True)
        embed.add_field(name="數量", value=f"**{prize_count}** 個", inline=True)
        if host:
            embed.add_field(name="主持人", value=host.mention, inline=False)

        winners_list = []
        for idx, user_id in enumerate(winner_ids, 1):
            winners_list.append(f"{idx}. <@{user_id}>")
        winners_mention = "\n".join(winners_list)
        embed.add_field(name="得獎名單", value=winners_mention, inline=False)

        embed.add_field(name="總參加人數", value=f"**{total_participants}** 人", inline=True)
        embed.add_field(name="中獎率", value=f"**{win_rate:.1f}%**", inline=True)

        giveaway_footer = self.config["embed"].get("footer", {})
        global_footer = self.global_embed_config.get("footer", {})

        footer_text = giveaway_footer.get("text") or global_footer.get("text")
        if footer_text:
            footer_icon = giveaway_footer.get("icon_url") or global_footer.get("icon_url") or None
            embed.set_footer(text=footer_text, icon_url=footer_icon)

        return embed

    @app_commands.command(name="giveaway", description="抽獎活動")
    async def giveaway(self, interaction: discord.Interaction) -> None:
        time_view = TimeSelectView(self)
        await interaction.response.send_message(
            "請選擇抽獎持續時間：", view=time_view, ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Giveaway(bot))
