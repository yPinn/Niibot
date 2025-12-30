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

    @app_commands.command(name="help", description="顯示所有可用指令")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Niibot 指令列表",
            description="以下是所有可用的斜線指令",
            color=discord.Color.blue()
        )

        # 工具指令
        embed.add_field(
            name="【工具指令】",
            value=(
                "`/ping` - 檢查 Bot 延遲\n"
                "`/info` - 顯示伺服器資訊\n"
                "`/userinfo` - 顯示用戶資訊\n"
                "`/avatar` - 顯示用戶頭像\n"
                "`/help` - 顯示此說明"
            ),
            inline=False
        )

        # 遊戲指令
        embed.add_field(
            name="【遊戲指令】",
            value=(
                "`/roll` - 擲骰子\n"
                "`/choose` - 隨機選擇\n"
                "`/8ball` - 神奇8號球\n"
                "`/coinflip` - 擲硬幣\n"
                "`/rps` - 猜拳遊戲"
            ),
            inline=False
        )

        # 占卜與抽獎
        embed.add_field(
            name="【占卜與抽獎】",
            value=(
                "`/fortune` - 今日運勢\n"
                "`/giveaway` - 建立抽獎活動"
            ),
            inline=False
        )

        # 餐點推薦
        embed.add_field(
            name="【餐點推薦】",
            value=(
                "`/eat` - 獲得餐點推薦\n"
                "`/categories` - 查看所有分類\n"
                "`/menu` - 查看分類菜單"
            ),
            inline=False
        )

        # 管理指令（需要權限）
        if isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.manage_messages:
            embed.add_field(
                name="【管理指令】（需要相應權限）",
                value=(
                    "`/clear` - 清除訊息\n"
                    "`/kick` - 踢出成員\n"
                    "`/ban` - 封鎖成員\n"
                    "`/unban` - 解除封鎖\n"
                    "`/mute` - 禁言成員\n"
                    "`/unmute` - 解除禁言\n"
                    "`/add_food` - 新增餐點\n"
                    "`/remove_food` - 移除餐點"
                ),
                inline=False
            )

        # 管理員專用
        if isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator:
            embed.add_field(
                name="【管理員專用】",
                value=(
                    "`/setlog` - 設定日誌頻道\n"
                    "`/unsetlog` - 取消日誌頻道設定\n"
                    "`/rate_stats` - 查看 API 速率限制統計\n"
                    "`/rate_check` - 檢查速率限制風險\n"
                    "`/delete_category` - 刪除餐點分類"
                ),
                inline=False
            )

        # Bot Owner 專用指令
        if interaction.user.id == self.bot.owner_id:
            embed.add_field(
                name="【Bot Owner 專用】",
                value=(
                    "`/reload` - 重載 Cog\n"
                    "`/load` - 載入 Cog\n"
                    "`/unload` - 卸載 Cog\n"
                    "`/cogs` - 列出已載入的 Cog\n"
                    "`/sync` - 同步指令樹"
                ),
                inline=False
            )

        embed.set_footer(text="使用 / 開頭來使用斜線指令")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="hello")
    async def hello_prefix(self, ctx: commands.Context):
        await ctx.send(f"你好，{ctx.author.mention}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
