"""Giveaway cog — background task and /giveaway slash command."""

from __future__ import annotations

import json
import logging
import random
from datetime import UTC, datetime
from typing import Any

import discord
from discord import app_commands, ui
from discord.ext import commands, tasks

from core import DATA_DIR

from ._embeds import create_giveaway_embed, create_result_embed
from ._persistence import GiveawayPersistence
from ._views import TimeSelectView

LOGGER = logging.getLogger(__name__)


class GiveawayCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._load_data()
        self._persistence = GiveawayPersistence(DATA_DIR / "active_giveaways.json")
        self.active_giveaways: dict[int, dict] = self._persistence.load()

    async def cog_load(self) -> None:
        self.check_giveaway_expiry.start()
        LOGGER.info("Giveaway expiry checker started")

    async def cog_unload(self) -> None:
        self.check_giveaway_expiry.cancel()
        LOGGER.info("Giveaway expiry checker stopped")

    def _load_data(self) -> None:
        with open(DATA_DIR / "giveaway.json", encoding="utf-8") as f:
            self.config = json.load(f)
        with open(DATA_DIR / "embed.json", encoding="utf-8") as f:
            self.global_embed_config = json.load(f)

    # ------------------------------------------------------------------
    # Persistence helpers (called by views)
    # ------------------------------------------------------------------

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
        await self._persistence.save(self.active_giveaways)

    async def remove_active_giveaway(self, message_id: int) -> None:
        if message_id in self.active_giveaways:
            del self.active_giveaways[message_id]
            await self._persistence.save(self.active_giveaways)

    async def update_participants(self, message_id: int, participants: list[int]) -> None:
        if message_id in self.active_giveaways:
            self.active_giveaways[message_id]["participants"] = participants
            await self._persistence.save(self.active_giveaways)

    # ------------------------------------------------------------------
    # Embed helpers (called by views and auto-end)
    # ------------------------------------------------------------------

    async def create_giveaway_embed(
        self,
        host: discord.User | discord.Member,
        prize_name: str,
        prize_count: int,
        description: str | None = None,
        end_time: datetime | None = None,
    ) -> discord.Embed:
        return create_giveaway_embed(
            config=self.config,
            global_config=self.global_embed_config,
            host=host,
            prize_name=prize_name,
            prize_count=prize_count,
            description=description,
            end_time=end_time,
        )

    async def create_result_embed(
        self,
        host: discord.Member | None,
        prize_name: str,
        prize_count: int,
        winner_ids: list[int],
        total_participants: int,
        host_avatar_url: str,
    ) -> discord.Embed:
        return create_result_embed(
            config=self.config,
            global_config=self.global_embed_config,
            host=host,
            prize_name=prize_name,
            prize_count=prize_count,
            winner_ids=winner_ids,
            total_participants=total_participants,
            host_avatar_url=host_avatar_url,
        )

    # ------------------------------------------------------------------
    # Background task
    # ------------------------------------------------------------------

    @tasks.loop(minutes=1)
    async def check_giveaway_expiry(self) -> None:
        now = datetime.now(UTC)
        expired = [
            (mid, data)
            for mid, data in self.active_giveaways.items()
            if now >= datetime.fromisoformat(data["end_time"])
        ]
        for message_id, data in expired:
            try:
                await self._auto_end_giveaway(message_id, data)
            except Exception as e:
                LOGGER.error(f"Failed to auto-end giveaway {message_id}: {e}")

    @check_giveaway_expiry.before_loop
    async def before_check_giveaway_expiry(self) -> None:
        await self.bot.wait_until_ready()

    async def _auto_end_giveaway(self, message_id: int, data: dict[str, Any]) -> None:
        try:
            channel = self.bot.get_channel(data["channel_id"])
            if not channel or not hasattr(channel, "fetch_message"):
                LOGGER.warning(f"Channel {data['channel_id']} not found for giveaway {message_id}")
                await self.remove_active_giveaway(message_id)
                return

            message = await channel.fetch_message(message_id)  # type: ignore[union-attr]
            if not message:
                LOGGER.warning(f"Message {message_id} not found")
                await self.remove_active_giveaway(message_id)
                return

            participants = data.get("participants", [])
            participant_count = len(participants)
            guild = self.bot.get_guild(data["guild_id"]) if data["guild_id"] else None
            host = guild.get_member(data["host_id"]) if guild else None

            # Rebuild a disabled view from the stored message components
            view = ui.View()
            for component in message.components:
                if hasattr(component, "children"):
                    for item in component.children:
                        if isinstance(item, discord.Button):
                            view.add_item(
                                ui.Button(
                                    label=item.label,
                                    style=item.style,
                                    disabled=True,
                                    custom_id=item.custom_id,
                                )
                            )

            if participant_count == 0:
                no_p_embed = discord.Embed(
                    title="【抽獎已截止】",
                    description="此抽獎已截止，但沒有人參加",
                    color=discord.Color.orange(),
                    timestamp=datetime.now(UTC),
                )
                no_p_embed.add_field(name="獎品", value=data["prize_name"], inline=True)
                no_p_embed.add_field(
                    name="數量", value=f"**{data['prize_count']}** 個", inline=True
                )
                if host:
                    no_p_embed.add_field(name="主持人", value=host.mention, inline=False)
                no_p_embed.add_field(name="參加人數", value="**0** 人", inline=False)
                await message.edit(embed=no_p_embed, view=view)
                await self.remove_active_giveaway(message_id)
                LOGGER.info(
                    f"Auto-ended giveaway {message_id} | Prize: {data['prize_name']} | No participants"
                )
                return

            winner_count = min(data["prize_count"], participant_count)
            winner_ids = random.sample(participants, winner_count)

            result_embed = create_result_embed(
                config=self.config,
                global_config=self.global_embed_config,
                host=host,
                prize_name=data["prize_name"],
                prize_count=data["prize_count"],
                winner_ids=winner_ids,
                total_participants=participant_count,
                host_avatar_url=data["host_avatar_url"],
            )

            await message.edit(embed=result_embed, view=view)

            winners_mention = " ".join([f"<@{uid}>" for uid in winner_ids])
            if hasattr(channel, "send"):
                await channel.send(
                    f"【抽獎結束】恭喜得獎者：{winners_mention}\n請查看上方抽獎結果！"
                )

            await self.remove_active_giveaway(message_id)
            LOGGER.info(
                f"Auto-ended giveaway {message_id} | Prize: {data['prize_name']} | "
                f"Participants: {participant_count} | Winners: {winner_count}"
            )

        except discord.NotFound:
            LOGGER.warning(f"Message {message_id} not found, removing from active giveaways")
            await self.remove_active_giveaway(message_id)
        except Exception as e:
            LOGGER.error(f"Error auto-ending giveaway {message_id}: {e}", exc_info=e)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @app_commands.command(name="giveaway", description="抽獎活動")
    async def giveaway(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "請選擇抽獎持續時間：", view=TimeSelectView(self), ephemeral=True
        )
