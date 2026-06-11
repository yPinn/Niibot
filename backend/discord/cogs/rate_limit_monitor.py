"""Rate limit monitoring commands"""

import discord
from discord import app_commands
from discord.ext import commands

from core import EmbedFactory


class RateLimitMonitorCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.rate_limiter = bot.rate_limiter  # type: ignore[attr-defined]
        self._embed = EmbedFactory.default()

    @app_commands.command(name="rate", description="Discord API 速率限制統計")
    @app_commands.default_permissions(administrator=True)
    async def rate(self, interaction: discord.Interaction) -> None:
        stats = self.rate_limiter.get_stats_summary()

        recent_rps = stats["recent_1min_rps"]
        max_rps = self.rate_limiter.GLOBAL_RATE_LIMIT
        usage_percent = (recent_rps / max_rps) * 100

        if usage_percent >= 90:
            status_text = "[CRITICAL]"
            color = discord.Color.red()
        elif usage_percent >= 70:
            status_text = "[WARNING]"
            color = discord.Color.orange()
        else:
            status_text = "[NORMAL]"
            color = discord.Color.green()

        embed = self._embed.build(
            title="Discord API 速率限制統計",
            color=color,
            timestamp=discord.utils.utcnow(),
        )

        embed.add_field(name="總請求數", value=f"`{stats['total_requests']:,}`", inline=True)
        embed.add_field(name="速率限制次數", value=f"`{stats['rate_limited_count']}`", inline=True)
        embed.add_field(name="當前狀態", value=status_text, inline=True)
        embed.add_field(
            name="最近1分鐘請求數", value=f"`{stats['recent_1min_requests']}`", inline=True
        )
        embed.add_field(
            name="最近1分鐘平均速率",
            value=f"`{recent_rps:.2f}` / `{max_rps}` req/s ({usage_percent:.1f}%)",
            inline=True,
        )

        if stats["recent_errors"]:
            error_text = "\n".join(
                [
                    f"- {err['bucket']}: retry {err['retry_after']:.1f}s"
                    for err in stats["recent_errors"]
                ]
            )
            embed.add_field(
                name="最近速率限制錯誤 (最多5個)",
                value=f"```\n{error_text}\n```" if error_text else "無",
                inline=False,
            )

        if usage_percent >= 90:
            embed.add_field(
                name="建議",
                value="速率使用率非常高，請檢查是否有過度請求的指令或功能",
                inline=False,
            )
        elif usage_percent >= 70:
            embed.add_field(name="提示", value="速率使用率偏高，建議關注請求頻率", inline=False)

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RateLimitMonitorCog(bot))
