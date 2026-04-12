"""Utility commands"""

import sys

import discord
from discord import app_commands
from discord.ext import commands

from core import BOT_NAME, BOT_VERSION


class UtilityCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Bot 延遲")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"延遲: {latency}ms")

    @app_commands.command(name="version", description="Bot 版本資訊")
    async def version(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(title=f"{BOT_NAME} 版本資訊", color=discord.Color.blue())

        python_version = (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        )

        embed.add_field(name="Bot 版本", value=f"`{BOT_VERSION}`", inline=True)
        embed.add_field(name="discord.py", value=f"`{discord.__version__}`", inline=True)
        embed.add_field(name="Python", value=f"`{python_version}`", inline=True)

        if self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        cog_count = len([ext for ext in self.bot.extensions.keys() if "cogs" in ext])
        embed.add_field(
            name="Bot 統計",
            value=(
                f"> 伺服器數: `{len(self.bot.guilds)}`\n"
                f"> 延遲: `{round(self.bot.latency * 1000)}ms`\n"
                f"> 已載入 Cogs: `{cog_count}`"
            ),
            inline=False,
        )

        embed.set_footer(text=f"Bot ID: {self.bot.user.id if self.bot.user else 'Unknown'}")
        await interaction.response.send_message(embed=embed)

    info = app_commands.Group(name="info", description="資訊查詢")

    @info.command(name="server", description="伺服器資訊")
    async def info_server(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("此指令只能在伺服器中使用", ephemeral=True)
            return

        embed = discord.Embed(
            title=guild.name, description=f"伺服器 ID: {guild.id}", color=discord.Color.blue()
        )

        embed.add_field(
            name="擁有者", value=guild.owner.mention if guild.owner else "未知", inline=True
        )
        embed.add_field(name="成員數", value=str(guild.member_count), inline=True)
        embed.add_field(name="頻道數", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="創建時間", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        await interaction.response.send_message(embed=embed)

    @info.command(name="user", description="用戶資訊")
    @app_commands.describe(member="要查詢的用戶（留空為自己）")
    async def info_user(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
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

    @info.command(name="avatar", description="用戶頭像")
    @app_commands.describe(member="要查詢的用戶（留空為自己）")
    async def info_avatar(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        target = member or interaction.user

        embed = discord.Embed(
            title=f"{target.display_name} 的頭像", color=target.color or discord.Color.default()
        )

        if target.avatar:
            embed.set_image(url=target.avatar.url)
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("此用戶沒有設定頭像", ephemeral=True)

    @app_commands.command(name="help", description="顯示所有指令")
    async def help(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Niibot 指令列表",
            description="以下是所有可用的斜線指令",
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="【工具指令】",
            value=(
                "`/ping` - Bot 延遲\n"
                "`/version` - Bot 版本資訊\n"
                "`/info server` - 伺服器資訊\n"
                "`/info user` - 用戶資訊\n"
                "`/info avatar` - 用戶頭像\n"
                "`/help` - 顯示此說明"
            ),
            inline=False,
        )

        embed.add_field(
            name="【遊戲指令】",
            value=(
                "`/game roll` - 擲骰子\n"
                "`/game choose` - 隨機選擇\n"
                "`/game rps` - 猜拳遊戲\n"
                "`/game roulette` - 俄羅斯輪盤"
            ),
            inline=False,
        )

        embed.add_field(
            name="【占卜與活動】",
            value=(
                "`/fortune` - 今日運勢\n"
                "`/tarot` - 每日塔羅\n"
                "`/giveaway` - 建立抽獎活動"
            ),
            inline=False,
        )

        embed.add_field(name="【AI 助手】", value="`/ai` - 向 AI 提問", inline=False)

        embed.add_field(
            name="【餐點推薦】",
            value=(
                "`/eat` - 餐點推薦選單\n"
                "`/food cat` - 列出所有分類\n"
                "`/food show` - 顯示分類內項目"
            ),
            inline=False,
        )

        embed.add_field(name="【TFT 戰棋】", value="`/tft` - 查詢 TFT 排行榜", inline=False)

        embed.add_field(
            name="【生日系統】", value="`/bday menu` - 生日功能選單（設定/訂閱/查看）", inline=False
        )

        if (
            isinstance(interaction.user, discord.Member)
            and interaction.user.guild_permissions.manage_messages
        ):
            embed.add_field(
                name="【管理指令】（需要相應權限）",
                value=(
                    "`/mod clear` - 清除訊息\n"
                    "`/mod kick` - 踢出成員\n"
                    "`/mod ban` - 封鎖成員\n"
                    "`/mod unban` - 解除封鎖\n"
                    "`/mod mute` - 禁言成員\n"
                    "`/mod unmute` - 解除禁言\n"
                    "`/food add` - 新增餐點\n"
                    "`/food remove` - 移除餐點"
                ),
                inline=False,
            )

        if (
            isinstance(interaction.user, discord.Member)
            and interaction.user.guild_permissions.administrator
        ):
            embed.add_field(
                name="【管理員專用】",
                value=(
                    "`/log set` - 設定日誌頻道\n"
                    "`/log unset` - 取消日誌頻道設定\n"
                    "`/rate` - 查看 API 速率限制統計\n"
                    "`/food delete` - 刪除餐點分類\n"
                    "`/bday init` - 初始化生日系統"
                ),
                inline=False,
            )

        if interaction.user.id == self.bot.owner_id:
            embed.add_field(
                name="【Bot Owner 專用】",
                value=(
                    "`/cog reload` - 重載 Cog\n"
                    "`/cog load` - 載入 Cog\n"
                    "`/cog unload` - 卸載 Cog\n"
                    "`/cog list` - 列出已載入的 Cog\n"
                    "`/cog sync` - 同步指令樹"
                ),
                inline=False,
            )

        embed.set_footer(text="使用 / 開頭來使用斜線指令")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UtilityCog(bot))
