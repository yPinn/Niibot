"""Utility commands"""

from discord.ext import commands

import discord
from discord import app_commands


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="檢查 Bot 延遲")
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"延遲: {latency}ms")

    @app_commands.command(name="info", description="顯示伺服器資訊")
    async def server_info(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("此指令只能在伺服器中使用")
            return

        embed = discord.Embed(
            title=guild.name, description=f"伺服器 ID: {guild.id}", color=discord.Color.blue()
        )

        embed.add_field(name="擁有者", value=guild.owner.mention if guild.owner else "未知", inline=True)
        embed.add_field(name="成員數", value=str(guild.member_count), inline=True)
        embed.add_field(name="頻道數", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="創建時間", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="顯示用戶資訊")
    @app_commands.describe(member="要查詢的用戶")
    async def user_info(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ):
        target = member or interaction.user

        embed = discord.Embed(
            title=f"{target.display_name} 的資訊", color=target.color or discord.Color.default()
        )

        embed.add_field(name="用戶名", value=str(target), inline=True)
        embed.add_field(name="ID", value=str(target.id), inline=True)

        if isinstance(target, discord.Member):
            embed.add_field(
                name="加入時間",
                value=target.joined_at.strftime("%Y-%m-%d") if target.joined_at else "未知",
                inline=True,
            )

        embed.add_field(name="帳號創建", value=target.created_at.strftime("%Y-%m-%d"), inline=True)

        if isinstance(target, discord.Member):
            roles = [role.mention for role in target.roles[1:]]
            if roles:
                embed.add_field(name="身分組", value=" ".join(roles[:10]), inline=False)

        if target.avatar:
            embed.set_thumbnail(url=target.avatar.url)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="顯示用戶頭像")
    @app_commands.describe(member="要查詢的用戶")
    async def avatar(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ):
        target = member or interaction.user

        embed = discord.Embed(
            title=f"{target.display_name} 的頭像", color=target.color or discord.Color.default()
        )

        if target.avatar:
            embed.set_image(url=target.avatar.url)
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("此用戶沒有設定頭像")

    @commands.command(name="hello")
    async def hello_prefix(self, ctx: commands.Context):
        await ctx.send(f"你好，{ctx.author.mention}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
