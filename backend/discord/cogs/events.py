"""Event logging for Discord server events"""

import logging
from datetime import datetime

from discord.ext import commands

import discord
from discord import app_commands

logger = logging.getLogger(__name__)


class Events(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log_channels: dict[int, int] = {}

    @app_commands.command(name="setlog", description="設定日誌")
    @app_commands.describe(channel="要設定為日誌頻道的文字頻道")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_log_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("此指令只能在伺服器中使用", ephemeral=True)
            return

        self.log_channels[interaction.guild.id] = channel.id
        await interaction.response.send_message(
            f"已設定日誌頻道為 {channel.mention}", ephemeral=True
        )
        logger.info(
            f"Log channel set | Guild: {interaction.guild.name} | Channel: #{channel.name} | By: {interaction.user.name}"
        )

    @app_commands.command(name="unsetlog", description="取消日誌")
    @app_commands.checks.has_permissions(administrator=True)
    async def unset_log_channel(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("此指令只能在伺服器中使用", ephemeral=True)
            return

        if interaction.guild.id in self.log_channels:
            del self.log_channels[interaction.guild.id]
            await interaction.response.send_message("已取消日誌頻道設定", ephemeral=True)
            logger.info(
                f"Log channel unset | Guild: {interaction.guild.name} | By: {interaction.user.name}"
            )
        else:
            await interaction.response.send_message("尚未設定日誌頻道", ephemeral=True)

    def get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        channel_id = self.log_channels.get(guild.id)
        if channel_id:
            channel = guild.get_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                return channel
        return None

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return

        log_channel = self.get_log_channel(message.guild)
        if not log_channel or log_channel == message.channel:
            return

        embed = discord.Embed(
            title="訊息刪除", color=discord.Color.orange(), timestamp=datetime.now()
        )
        embed.add_field(name="作者", value=message.author.mention, inline=True)

        channel_name = (
            message.channel.mention if hasattr(message.channel, "mention") else str(message.channel)
        )
        embed.add_field(name="頻道", value=channel_name, inline=True)

        content = message.content[:1024] if message.content else "無文字內容"
        embed.add_field(name="內容", value=content, inline=False)

        if message.attachments:
            attachments_text = "\n".join([att.filename for att in message.attachments[:5]])
            embed.add_field(name="附件", value=attachments_text, inline=False)

        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.author.bot or not before.guild or before.content == after.content:
            return

        log_channel = self.get_log_channel(before.guild)
        if not log_channel or log_channel == before.channel:
            return

        embed = discord.Embed(
            title="訊息編輯", color=discord.Color.blue(), timestamp=datetime.now()
        )
        embed.add_field(name="作者", value=before.author.mention, inline=True)

        channel_name = (
            before.channel.mention if hasattr(before.channel, "mention") else str(before.channel)
        )
        embed.add_field(name="頻道", value=channel_name, inline=True)

        before_content = before.content[:512] if before.content else "無內容"
        after_content = after.content[:512] if after.content else "無內容"

        embed.add_field(name="編輯前", value=before_content, inline=False)
        embed.add_field(name="編輯後", value=after_content, inline=False)
        embed.add_field(name="跳轉", value=f"[查看訊息]({after.jump_url})", inline=False)

        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        log_channel = self.get_log_channel(before.guild)
        if not log_channel:
            return

        changes = []

        if before.nick != after.nick:
            changes.append(f"暱稱: `{before.nick or '無'}` → `{after.nick or '無'}`")

        if before.roles != after.roles:
            added_roles = [role for role in after.roles if role not in before.roles]
            removed_roles = [role for role in before.roles if role not in after.roles]

            if added_roles:
                changes.append(f"新增身分組: {', '.join([r.mention for r in added_roles])}")
            if removed_roles:
                changes.append(f"移除身分組: {', '.join([r.mention for r in removed_roles])}")

        if changes:
            embed = discord.Embed(
                title="成員資訊更新",
                description=f"{after.mention} 的資訊已更新",
                color=discord.Color.purple(),
                timestamp=datetime.now(),
            )
            embed.add_field(name="用戶", value=str(after), inline=False)
            embed.add_field(name="變更內容", value="\n".join(changes), inline=False)

            await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]) -> None:
        if not messages or not messages[0].guild:
            return

        guild = messages[0].guild
        log_channel = self.get_log_channel(guild)
        if not log_channel:
            return

        channel_name = (
            messages[0].channel.mention
            if hasattr(messages[0].channel, "mention")
            else str(messages[0].channel)
        )

        embed = discord.Embed(
            title="批量訊息刪除",
            description=f"在 {channel_name} 刪除了 {len(messages)} 則訊息",
            color=discord.Color.red(),
            timestamp=datetime.now(),
        )

        await log_channel.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Events(bot))
