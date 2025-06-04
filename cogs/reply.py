import discord
from discord.ext import commands

import random
from utils import util


class Reply(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.target_role_id = 1378242954929639514  # 直接寫在 class 內
        self.reply_msgs_path = "data/reply_msgs.json"
        self.reply_msgs = []

    async def load_reply_msgs(self):
        try:
            msgs = await util.read_json(self.reply_msgs_path)
            self.reply_msgs = msgs if isinstance(
                msgs, list) and msgs else self.default_msgs()
        except Exception as e:
            print(f"[Reply] failed to load msgs: {e}")
            self.reply_msgs = self.default_msgs()

    def default_msgs(self):
        return [
            "不要 @ 我，幹你娘！！！",
            "不熟N標",
            "?",
            "幹你娘機掰標三小",
            "皮 ↘ 炎 ↗",
            "uu：愛是寂寞人",
            "不要再冒充我的身分了",
        ]

    async def handle_on_message(self, message: discord.Message):
        # 不回應機器人自己
        if message.author.bot:
            return

        # 例如：當訊息中含有特定關鍵字或符合某條件時，隨機回覆
        keywords = ["@機器人", "呼叫", "喂"]
        if any(k in message.content for k in keywords):
            if self.reply_msgs:
                reply = random.choice(self.reply_msgs)
                await message.channel.send(reply)

    @commands.Cog.listener()
    async def on_ready(self):
        await self.load_reply_msgs()

<<<<<<< HEAD
    # @commands.Cog.listener()
    # async def on_message(self, message: discord.Message):
    #     """監聽訊息，當被指定角色標註時隨機回覆"""
    #     if message.author.bot:
    #         return  # 忽略機器人訊息

    #     mentioned_role_ids = [role.id for role in message.role_mentions]
    #     if self.target_role_id in mentioned_role_ids:
    #         reply_text = random.choice(self.reply_msgs)
    #         # 利用 util.format_success_msg 統一格式
    #         reply_text = util.format_success_msg(reply_text)
    #         await message.reply(reply_text, mention_author=True)

    #     # 確保其他命令正常運行
    #     await self.bot.process_commands(message)

=======
>>>>>>> dev
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
                    await ctx.send(util.format_error_msg("請提供有效的用戶 ID、名稱或 @提及"))
                    return
                except discord.NotFound:
                    await ctx.send(util.format_error_msg("找不到該用戶"))
                    return

        if user is None:
            await ctx.send(util.format_error_msg("找不到該用戶，請確認輸入是否正確"))
            return

        avatar_url = user.display_avatar.url
        banner_url = None
        accent_color = None
        try:
            fetched_user = await self.bot.fetch_user(user.id)
            banner_url = getattr(fetched_user.banner, "url", None)
            accent_color = fetched_user.accent_color
        except Exception:
            pass

        embed = discord.Embed(
            title=f"{user.display_name} 的資料",
            color=accent_color or discord.Color.green(),
            timestamp=util.now_utc(),
        )
        embed.set_author(
            name="Ditto",
            icon_url="https://i.pinimg.com/736x/41/0b/a5/410ba54a0c7ca00f359d008f4fcebcd0.jpg",
        )
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

        embed.set_footer(
            text="Niibot",
            icon_url=(
                self.bot.user.display_avatar.url if self.bot.user else discord.Embed.Empty),
        )

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    reply = Reply(bot)
    await reply.load_reply_msgs()
    await bot.add_cog(reply)
    bot.reply = reply  # 方便 Listener 拿到
