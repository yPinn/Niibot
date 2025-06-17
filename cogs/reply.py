import asyncio
import random

import discord
from discord import app_commands
from discord.ext import commands

from utils import util
from utils.logger import BotLogger
from utils.config_manager import config


class Reply(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.target_role_id = config.target_role_id
        self.data_file = "reply_msgs.json"
        self.reply_msgs = []

    async def load_reply_msgs(self):
        try:
            data = await util.read_json(util.get_data_file_path(self.data_file))
            self.reply_msgs = data if isinstance(data, list) and data else self.default_msgs()
            if not data:  # 如果檔案為空，儲存預設訊息
                await util.write_json(util.get_data_file_path(self.data_file), self.reply_msgs)
            BotLogger.info("Reply", f"載入了 {len(self.reply_msgs)} 條回覆訊息")
        except Exception as e:
            BotLogger.error("Reply", "載入回覆訊息失敗", e)
            self.reply_msgs = self.default_msgs()

    def default_msgs(self):
        return [
            "不要 @ 我，白目嗎！！！",
            "不熟N標",
            "?",
            # "幹你娘機掰標三小",
            "皮 ↘ 炎 ↗",
            # "uu：愛是寂寞人",
            "不要再冒充我的身分了",
            "請問你誰？交叉燒查榜除了我以外沒有同時需要考慮這兩間麵店的..如果你是要分顆肉包 那真心祝你加油粿 而且你也昨天搶票 如果你是真人希望有機會能成為志同道合作社的朋友 但如果你是用我的身分起號 我覺得有點噁心 如果有冒犯到你的話很抱歉，只是因為你連帳號都跟我很像、通通跟我一樣才有點敏感"
        ]

    async def handle_on_message(self, message: discord.Message):
        # 不回應機器人自己
        if message.author.bot:
            return

        # 忽略指令訊息（避免與機器人指令衝突）
        from utils.config_manager import config
        prefixes = config.command_prefix if isinstance(config.command_prefix, list) else [config.command_prefix]
        if any(message.content.startswith(prefix) for prefix in prefixes):
            return

        # 除錯用：可以啟用以追蹤方法調用
        # BotLogger.debug("Reply", f"處理訊息: {message.author.display_name}")

        # 原本的關鍵字條件
        keywords = ["呼叫"]
        match_keyword = any(k in message.content for k in keywords)

        # 新增：提及指定身分組的條件
        match_role_mention = any(
            role.id == self.target_role_id for role in message.role_mentions)

        # 如果符合任一條件，隨機回覆
        if match_keyword or match_role_mention:
            if self.reply_msgs:
                reply = random.choice(self.reply_msgs)
                await message.reply(reply, mention_author=False)
                
                # 記錄觸發情況
                trigger_type = "關鍵字" if match_keyword else "身分組提及"
                BotLogger.user_action(
                    "回覆觸發", 
                    message.author.id, 
                    message.guild.id if message.guild else 0,
                    f"觸發類型: {trigger_type}, 訊息: {util.truncate_text(message.content)}"
                )

    @commands.Cog.listener()
    async def on_ready(self):
        await self.load_reply_msgs()

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
                    error_msg = "請提供有效的用戶 ID、名稱或 @提及"
                    await ctx.send(util.format_error_msg(error_msg))
                    BotLogger.command_used("cc", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"錯誤: {error_msg}")
                    return
                except discord.NotFound:
                    error_msg = "找不到該用戶"
                    await ctx.send(util.format_error_msg(error_msg))
                    BotLogger.command_used("cc", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"錯誤: {error_msg}")
                    return

        if user is None:
            error_msg = "找不到該用戶，請確認輸入是否正確"
            await ctx.send(util.format_error_msg(error_msg))
            BotLogger.command_used("cc", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"錯誤: {error_msg}")
            return

        avatar_url = user.display_avatar.url
        banner_url = None
        accent_color = None
        try:
            fetched_user = await self.bot.fetch_user(user.id)
            banner_url = getattr(fetched_user.banner, "url", None)
            accent_color = fetched_user.accent_color
        except Exception as e:
            BotLogger.warning("Reply", f"取得用戶 {user.id} 的詳細資料失敗", e)

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
        
        # 記錄成功的指令使用
        BotLogger.command_used(
            "cc", 
            ctx.author.id, 
            ctx.guild.id if ctx.guild else 0, 
            f"目標用戶: {user.display_name} ({user.id})"
        )

    @copycat.error
    async def copycat_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ 請提供用戶資訊，例如：`?cc @用戶名` 或 `?cc 用戶ID` 或 `?cc 用戶名稱`")
        else:
            BotLogger.error("Reply", f"cc 指令錯誤: {error}")

    # 斜線指令版本
    @app_commands.command(name="copycat", description="複製用戶的頭像和橫幅")
    @app_commands.describe(user="要複製的用戶")
    async def slash_copycat(self, interaction: discord.Interaction, user: discord.User):
        """斜線指令版本的 copycat"""
        try:
            # 嘗試獲取完整的用戶信息以便獲取橫幅
            try:
                full_user = await self.bot.fetch_user(user.id)
            except:
                full_user = user

            embed = discord.Embed(
                title=f"🎭 {full_user.display_name}",
                color=discord.Color.blurple()
            )

            # 設置頭像
            if full_user.display_avatar:
                embed.set_image(url=full_user.display_avatar.url)
                embed.add_field(
                    name="🖼️ 頭像",
                    value=f"[點擊查看]({full_user.display_avatar.url})",
                    inline=True
                )

            # 設置橫幅（如果有的話）
            if hasattr(full_user, 'banner') and full_user.banner:
                embed.set_thumbnail(url=full_user.banner.url)
                embed.add_field(
                    name="🎨 橫幅",
                    value=f"[點擊查看]({full_user.banner.url})",
                    inline=True
                )
            else:
                embed.add_field(
                    name="🎨 橫幅",
                    value="無橫幅",
                    inline=True
                )

            # 添加用戶資訊
            embed.add_field(
                name="👤 用戶資訊",
                value=f"**用戶名**: {full_user.name}\n**ID**: {full_user.id}",
                inline=False
            )

            # 設置創建時間
            embed.timestamp = full_user.created_at
            embed.set_footer(
                text="Niibot",
                icon_url=(
                    self.bot.user.display_avatar.url if self.bot.user else discord.Embed.Empty),
            )

            await interaction.response.send_message(embed=embed)
            
            # 記錄成功的指令使用
            BotLogger.command_used(
                "copycat", 
                interaction.user.id, 
                interaction.guild.id if interaction.guild else 0, 
                f"目標用戶: {full_user.display_name} ({full_user.id})"
            )
            
        except discord.NotFound:
            await interaction.response.send_message("❌ 找不到該用戶，請確認輸入是否正確", ephemeral=True)
        except Exception as e:
            BotLogger.error("Reply", f"slash copycat 指令錯誤: {e}")
            if interaction.response.is_done():
                await interaction.followup.send("❌ 系統發生錯誤，請稍後再試。", ephemeral=True)
            else:
                await interaction.response.send_message("❌ 系統發生錯誤，請稍後再試。", ephemeral=True)


async def setup(bot: commands.Bot):
    reply = Reply(bot)
    # 同步載入資料，確保載入完成後才開始處理訊息
    await reply.load_reply_msgs()
    await bot.add_cog(reply)
    BotLogger.system_event("Cog載入", "Reply cog 已成功載入")
