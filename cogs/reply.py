import datetime
import random

import discord
from discord.ext import commands


class Reply(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        target_role_id = 1378242954929639514  # 這是 "陳玥黎" 的角色 ID
        target_user_id = 478194275360964608  # 這是 "31" 的 ID

        mentioned_role_ids = [role.id for role in message.role_mentions]
        mentioned_user_ids = [user.id for user in message.mentions]

        msg = [
            "不要 @ 我，幹你娘！！！",
            "不熟N標",
            "?",
            "幹你娘機掰標三小",
            "皮 ↘ 炎 ↗",
            f"不用標 標<@{target_user_id}>就好",
            "uu：愛是寂寞人",
            "不要再冒充我的身分了",
        ]

        if target_role_id in mentioned_role_ids or target_user_id in mentioned_user_ids:
            await message.reply(random.choice(msg), mention_author=True)

    @commands.command(name="cc", aliases=["複製", "ditto"], help="複製人，顯示頭像和橫幅")
    async def copycat(self, ctx: commands.Context, *, user_input: str):
        user = None

        if ctx.message.mentions:
            user = ctx.message.mentions[0]
        else:
            if ctx.guild:
                user = discord.utils.find(
                    lambda m: m.name == user_input or m.display_name == user_input,
                    ctx.guild.members,
                )
            if not user:
                try:
                    user_id = int(user_input)
                    user = ctx.guild.get_member(user_id) if ctx.guild else None
                    if user is None:
                        user = await self.bot.fetch_user(user_id)
                except ValueError:
                    await ctx.send(
                        embed=discord.Embed(
                            description="⚠️ 請提供有效的用戶 ID、名稱或 @提及",
                            color=discord.Color.red(),
                        )
                    )
                    return
                except discord.NotFound:
                    await ctx.send("⚠️ 找不到該用戶")
                    return

        if user is None:
            await ctx.send("⚠️ 找不到該用戶，請確認輸入是否正確")
            return

        avatar_url = user.display_avatar.url

        banner_url = None
        accent_color = None
        try:
            fetched_user = await self.bot.fetch_user(user.id)
            banner_url = fetched_user.banner.url if fetched_user.banner else None
            accent_color = fetched_user.accent_color
        except Exception:
            pass

        embed_color = accent_color if accent_color else discord.Color.green()

        embed = discord.Embed(
            title=f"{user.display_name} 的資料",
            color=embed_color,
            timestamp=datetime.datetime.now(),
        )

        embed.set_author(
            name="Ditto", icon_url="https://i.pinimg.com/736x/41/0b/a5/410ba54a0c7ca00f359d008f4fcebcd0.jpg")
        embed.set_thumbnail(url=avatar_url)
        embed.add_field(name="頭像", value=f"[點我查看]({avatar_url})", inline=False)

        if banner_url:
            embed.set_image(url=banner_url)
            embed.add_field(
                name="橫幅", value=f"[點我查看]({banner_url})", inline=False)
        else:
            embed.add_field(name="橫幅", value="無橫幅", inline=False)

        if accent_color:
            embed.add_field(name="主題顏色", value=str(accent_color), inline=False)

        embed.set_footer(text="Niibot", icon_url=self.bot.user.avatar.url)

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Reply(bot))
