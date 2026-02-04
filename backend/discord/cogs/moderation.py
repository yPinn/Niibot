"""Server moderation commands"""

from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="clear", description="清除訊息")
    @app_commands.describe(amount="要清除的訊息數量")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, amount: int) -> None:
        if amount < 1 or amount > 100:
            await interaction.response.send_message("數量必須在 1-100 之間", ephemeral=True)
            return

        if not isinstance(
            interaction.channel,
            (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.Thread),
        ):
            await interaction.response.send_message("此頻道類型不支援清除訊息", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"已清除 {len(deleted)} 則訊息", ephemeral=True)

    @app_commands.command(name="kick", description="踢出成員")
    @app_commands.describe(member="要踢出的成員", reason="踢出原因")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(
        self, interaction: discord.Interaction, member: discord.Member, reason: str | None = None
    ) -> None:
        if isinstance(interaction.user, discord.Member):
            if member.top_role >= interaction.user.top_role:
                await interaction.response.send_message("你無法踢出此成員", ephemeral=True)
                return

        try:
            await member.kick(reason=reason or "未提供原因")
            await interaction.response.send_message(f"已踢出 {member.mention}")
        except discord.Forbidden:
            await interaction.response.send_message("我沒有權限踢出此成員", ephemeral=True)

    @app_commands.command(name="ban", description="封鎖成員")
    @app_commands.describe(member="要封鎖的成員", reason="封鎖原因")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(
        self, interaction: discord.Interaction, member: discord.Member, reason: str | None = None
    ) -> None:
        if isinstance(interaction.user, discord.Member):
            if member.top_role >= interaction.user.top_role:
                await interaction.response.send_message("你無法封鎖此成員", ephemeral=True)
                return

        try:
            await member.ban(reason=reason or "未提供原因")
            await interaction.response.send_message(f"已封鎖 {member.mention}")
        except discord.Forbidden:
            await interaction.response.send_message("我沒有權限封鎖此成員", ephemeral=True)

    @app_commands.command(name="unban", description="解除封鎖")
    @app_commands.describe(user_id="要解除封鎖的用戶 ID")
    @app_commands.checks.has_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str) -> None:
        if not interaction.guild:
            await interaction.response.send_message("此指令只能在伺服器中使用", ephemeral=True)
            return

        try:
            user = await self.bot.fetch_user(int(user_id))
            await interaction.guild.unban(user)
            await interaction.response.send_message(f"已解除封鎖: {user}")
        except ValueError:
            await interaction.response.send_message("無效的用戶 ID", ephemeral=True)
        except discord.NotFound:
            await interaction.response.send_message("找不到此用戶或未被封鎖", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("我沒有權限解除封鎖", ephemeral=True)

    @app_commands.command(name="mute", description="禁言成員")
    @app_commands.describe(member="要禁言的成員", duration="禁言時長（分鐘）", reason="禁言原因")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: int,
        reason: str | None = None,
    ) -> None:
        if isinstance(interaction.user, discord.Member):
            if member.top_role >= interaction.user.top_role:
                await interaction.response.send_message("你無法禁言此成員", ephemeral=True)
                return

        if duration < 1 or duration > 40320:
            await interaction.response.send_message("時長必須在 1-40320 分鐘之間", ephemeral=True)
            return

        try:
            await member.timeout(timedelta(minutes=duration), reason=reason or "未提供原因")
            await interaction.response.send_message(f"已禁言 {member.mention} {duration} 分鐘")
        except discord.Forbidden:
            await interaction.response.send_message("我沒有權限禁言此成員", ephemeral=True)

    @app_commands.command(name="unmute", description="解除禁言")
    @app_commands.describe(member="要解除禁言的成員")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unmute(self, interaction: discord.Interaction, member: discord.Member) -> None:
        try:
            await member.timeout(None)
            await interaction.response.send_message(f"已解除禁言: {member.mention}")
        except discord.Forbidden:
            await interaction.response.send_message("我沒有權限解除禁言", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
