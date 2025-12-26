"""
速率限制監控命令
提供速率限制統計和警告功能
"""

from discord.ext import commands

import discord
from discord import app_commands


class RateLimitMonitorCog(commands.Cog):
    """速率限制監控命令"""

    def __init__(self, bot):
        self.bot = bot
        self.rate_limiter = bot.rate_limiter

    @app_commands.command(name="rate_stats", description="查看 Discord API 速率限制統計")
    @app_commands.default_permissions(administrator=True)
    async def rate_stats(self, interaction: discord.Interaction):
        """顯示速率限制統計資訊"""
        stats = self.rate_limiter.get_stats_summary()

        embed = discord.Embed(
            title="📊 Discord API 速率限制統計",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )

        # 基本統計
        embed.add_field(
            name="總請求數",
            value=f"`{stats['total_requests']:,}`",
            inline=True
        )

        embed.add_field(
            name="速率限制次數",
            value=f"`{stats['rate_limited_count']}`",
            inline=True
        )

        # 最近1分鐘的速率
        recent_rps = stats['recent_1min_rps']
        max_rps = self.rate_limiter.GLOBAL_RATE_LIMIT
        usage_percent = (recent_rps / max_rps) * 100

        # 根據使用率選擇顏色
        if usage_percent >= 90:
            status_emoji = "🔴"
            status_text = "危險"
        elif usage_percent >= 70:
            status_emoji = "🟡"
            status_text = "警告"
        else:
            status_emoji = "🟢"
            status_text = "正常"

        embed.add_field(
            name="當前狀態",
            value=f"{status_emoji} {status_text}",
            inline=True
        )

        embed.add_field(
            name="最近1分鐘請求數",
            value=f"`{stats['recent_1min_requests']}`",
            inline=True
        )

        embed.add_field(
            name="最近1分鐘平均速率",
            value=f"`{recent_rps:.2f}` / `{max_rps}` req/s ({usage_percent:.1f}%)",
            inline=True
        )

        # 最近錯誤
        if stats['recent_errors']:
            error_text = "\n".join([
                f"• `{err['bucket']}` - 等待 {err['retry_after']:.1f}s"
                for err in stats['recent_errors']
            ])
            embed.add_field(
                name="最近速率限制錯誤 (最多顯示5個)",
                value=error_text or "無",
                inline=False
            )

        # 健康建議
        if usage_percent >= 90:
            embed.add_field(
                name="⚠️  建議",
                value="速率使用率非常高！請檢查是否有過度請求的指令或功能。",
                inline=False
            )
        elif usage_percent >= 70:
            embed.add_field(
                name="💡 提示",
                value="速率使用率偏高，建議關注請求頻率。",
                inline=False
            )

        embed.set_footer(text=f"Bot: {self.bot.user.name}")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rate_check", description="檢查當前速率限制風險")
    @app_commands.default_permissions(administrator=True)
    async def rate_check(self, interaction: discord.Interaction):
        """檢查當前的速率限制風險"""
        is_safe, message = self.rate_limiter.check_rate_limit_risk()

        if is_safe:
            color = discord.Color.green()
            title = "✅ 速率檢查通過"
        else:
            color = discord.Color.red()
            title = "⛔ 速率風險警告"

        embed = discord.Embed(
            title=title,
            description=message,
            color=color,
            timestamp=discord.utils.utcnow()
        )

        # 顯示限制參考值
        embed.add_field(
            name="全局限制",
            value=f"`{self.rate_limiter.GLOBAL_RATE_LIMIT}` req/s",
            inline=True
        )

        embed.add_field(
            name="訊息限制",
            value=f"`{self.rate_limiter.MESSAGE_RATE_LIMIT}` msg/5s/channel",
            inline=True
        )

        embed.add_field(
            name="反應限制",
            value=f"`{int(1/0.25)}` reactions/s",
            inline=True
        )

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    """載入 Cog"""
    await bot.add_cog(RateLimitMonitorCog(bot))
