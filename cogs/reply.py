import asyncio
import random

import discord
from discord import app_commands
from discord.ext import commands

from utils import util
from utils.logger import BotLogger
from utils.config_manager import config


class CopycatToggleView(discord.ui.View):
    """簡化版Copycat切換介面 - 單一按鈕切換主要/伺服器"""
    
    def __init__(self, user, guild, bot, author_id, timeout=300):
        super().__init__(timeout=timeout)
        self.user = user
        self.guild = guild
        self.bot = bot
        self.author_id = author_id
        self.message = None
        self.show_guild = True  # 預設顯示伺服器設定（如果有的話）
        
        # 檢查是否有伺服器專用設定
        self.has_guild_settings = self._check_guild_settings()
        
        # 如果沒有伺服器設定，預設顯示主要設定並鎖定按鈕
        if not self.has_guild_settings:
            self.show_guild = False
            # 移除所有按鈕並添加鎖定按鈕
            self.clear_items()
            self.add_item(self.create_locked_button())
    
    def _check_guild_settings(self):
        """檢查用戶是否有伺服器專用設定"""
        if not self.guild or not isinstance(self.user, discord.Member):
            return False
        
        # 檢查guild_avatar
        has_guild_avatar = hasattr(self.user, 'guild_avatar') and self.user.guild_avatar is not None
        
        # 檢查guild_banner (目前Discord可能尚未支援，但為未來準備)
        has_guild_banner = hasattr(self.user, 'guild_banner') and self.user.guild_banner is not None
        
        return has_guild_avatar or has_guild_banner
    
    def create_locked_button(self):
        """創建鎖定狀態的按鈕"""
        button = discord.ui.Button(
            label="🔒 無伺服器設定",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            custom_id="locked_button"
        )
        return button
    
    async def get_user_assets(self, use_guild=True):
        """獲取用戶資產（頭像、橫幅、主題顏色）"""
        assets = {
            'avatar_url': None,
            'banner_url': None,
            'accent_color': None
        }
        
        try:
            if use_guild and self.guild and isinstance(self.user, discord.Member) and self.has_guild_settings:
                # 伺服器設定模式
                # 優先使用guild_avatar，沒有則使用主要avatar
                if hasattr(self.user, 'guild_avatar') and self.user.guild_avatar:
                    assets['avatar_url'] = self.user.guild_avatar.url
                else:
                    assets['avatar_url'] = self.user.display_avatar.url
                
                # 檢查guild_banner (目前Discord可能尚未支援，預留功能)
                if hasattr(self.user, 'guild_banner') and self.user.guild_banner:
                    assets['banner_url'] = self.user.guild_banner.url
                    # 伺服器banner通常不包含accent_color，所以不需要fetch
                else:
                    # 如果沒有guild_banner，獲取主要banner和accent_color
                    try:
                        fetched_user = await self.bot.fetch_user(self.user.id)
                        if hasattr(fetched_user, 'banner') and fetched_user.banner:
                            assets['banner_url'] = fetched_user.banner.url
                        assets['accent_color'] = fetched_user.accent_color
                    except (discord.NotFound, discord.HTTPException) as e:
                        BotLogger.warning("Reply", f"無法獲取用戶 {self.user.id} 的詳細資料: {e}")
                    except Exception as e:
                        BotLogger.warning("Reply", f"獲取用戶 {self.user.id} 詳細資料時發生未預期錯誤", e)
            else:
                # 主要設定模式
                assets['avatar_url'] = self.user.display_avatar.url
                
                try:
                    # 避免重複fetch，如果user已經是完整的User對象就直接使用
                    if hasattr(self.user, 'banner') and hasattr(self.user, 'accent_color'):
                        fetched_user = self.user
                    else:
                        fetched_user = await self.bot.fetch_user(self.user.id)
                    
                    if hasattr(fetched_user, 'banner') and fetched_user.banner:
                        assets['banner_url'] = fetched_user.banner.url
                    assets['accent_color'] = fetched_user.accent_color
                    
                except (discord.NotFound, discord.HTTPException) as e:
                    BotLogger.warning("Reply", f"無法獲取用戶 {self.user.id} 的詳細資料: {e}")
                except Exception as e:
                    BotLogger.warning("Reply", f"獲取用戶 {self.user.id} 詳細資料時發生未預期錯誤", e)
        
        except Exception as e:
            BotLogger.error("Reply", f"獲取用戶資產時發生嚴重錯誤", e)
            # 使用最基本的備用方案
            assets['avatar_url'] = self.user.display_avatar.url if self.user else None
        
        # 確保至少有基本的avatar
        if not assets['avatar_url']:
            assets['avatar_url'] = self.user.default_avatar.url if self.user else None
        
        return assets
    
    async def create_embed(self):
        """創建embed（保持原有UI格式）"""
        assets = await self.get_user_assets(self.show_guild)
        
        embed = discord.Embed(
            title=f"{self.user.display_name} 的資料",
            color=assets['accent_color'] or discord.Color.green(),
            timestamp=util.now_utc(),
        )
        embed.set_author(
            name="Ditto",
            icon_url="https://i.pinimg.com/736x/41/0b/a5/410ba54a0c7ca00f359d008f4fcebcd0.jpg",
        )
        
        # 設置頭像
        if assets['avatar_url']:
            embed.set_thumbnail(url=assets['avatar_url'])
            embed.add_field(name="頭像", value=f"[點我查看]({assets['avatar_url']})", inline=False)
        
        # 設置橫幅
        if assets['banner_url']:
            embed.set_image(url=assets['banner_url'])
            embed.add_field(name="橫幅", value=f"[點我查看]({assets['banner_url']})", inline=False)
        else:
            embed.add_field(name="橫幅", value="無橫幅", inline=False)
        
        # 設置主題顏色
        if assets['accent_color']:
            embed.add_field(name="主題顏色", value=str(assets['accent_color']), inline=False)
        
        embed.set_footer(
            text="Niibot",
            icon_url=(self.bot.user.display_avatar.url if self.bot.user else discord.Embed.Empty),
        )
        
        return embed
    
    @discord.ui.button(label="🔄 切換為主要", style=discord.ButtonStyle.primary)
    async def toggle_setting(self, interaction: discord.Interaction, button: discord.ui.Button):
        """切換按鈕處理"""
        # 權限檢查
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ 只有指令發起者可以操作", ephemeral=True)
            return
        
        try:
            # 切換顯示模式
            self.show_guild = not self.show_guild
            
            # 更新按鈕文字
            if self.show_guild:
                button.label = "🔄 切換為主要"
            else:
                button.label = "🔄 切換為伺服器"
            
            # 更新embed
            embed = await self.create_embed()
            
            # 安全的回應處理
            if interaction.response.is_done():
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)
                
            # 記錄切換動作
            BotLogger.info("Reply", f"用戶 {interaction.user.id} 切換copycat顯示為: {'伺服器' if self.show_guild else '主要'}")
            
        except discord.NotFound:
            await interaction.response.send_message("❌ 訊息已被刪除，無法更新", ephemeral=True)
        except discord.HTTPException as e:
            BotLogger.error("Reply", f"Discord API錯誤: {e}")
            try:
                await interaction.response.send_message("❌ 更新失敗，請重新使用指令", ephemeral=True)
            except:
                pass
        except Exception as e:
            BotLogger.error("Reply", f"切換設定時發生未預期錯誤", e)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ 切換時發生錯誤，請稍後再試", ephemeral=True)
                else:
                    await interaction.followup.send("❌ 切換時發生錯誤，請稍後再試", ephemeral=True)
            except:
                pass
    
    async def on_timeout(self):
        """按鈕逾時處理"""
        try:
            for item in self.children:
                item.disabled = True
            
            if self.message:
                await self.message.edit(view=self)
        except Exception as e:
            BotLogger.warning("Reply", f"處理按鈕逾時時發生錯誤", e)


class Reply(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.target_role_id = config.target_role_id
        self.data_file = "reply_msgs.json"
        self.reply_msgs = []

    async def load_reply_msgs(self):
        try:
            data = await util.read_json(util.get_data_file_path(self.data_file))
            self.reply_msgs = data if isinstance(
                data, list) and data else self.default_msgs()
            if not data:  # 如果檔案為空，儲存預設訊息
                await util.write_json(util.get_data_file_path(self.data_file), self.reply_msgs)
            BotLogger.info("Reply", f"載入了 {len(self.reply_msgs)} 條回覆訊息")
        except Exception as e:
            BotLogger.error("Reply", "載入回覆訊息失敗", e)
            self.reply_msgs = self.default_msgs()

    def default_msgs(self):
        return [
            "不要 @ 我，白目嗎！！！",
        ]

    async def handle_on_message(self, message: discord.Message):
        # 不回應機器人自己
        if message.author.bot:
            return

        # 忽略指令訊息（避免與機器人指令衝突）
        from utils.config_manager import config
        prefixes = config.command_prefix if isinstance(
            config.command_prefix, list) else [config.command_prefix]
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

    @commands.command(name="milktea", aliases=["珍珠", "抹茶", "奶茶"], help="https://www.twitch.tv/31xuy/clip/SuccessfulNastyWitchPraiseIt-k85ZcLWoG7qjo0yR")
    async def matcha_milktea(self, ctx: commands.Context):
        text = f"他幹嘛啦 😰 他@#$%^&*（咕嚕咕嚕 💦）\n珍珠抹茶奶茶要怎麼做啦 😓\n珍珠抹茶奶茶 😰 不要關我燈 😨\n他長得很恐怖啦 👻 他長得很恐怖啦 😱\n哇 😓 珍珠抹茶奶茶 😰 珍珠抹茶奶茶 😥\n啊 😱 啊 💀 啊 😰 啊 👻 啊 😵"
        await ctx.reply(text)

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
                    BotLogger.command_used(
                        "cc", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"錯誤: {error_msg}")
                    return
                except discord.NotFound:
                    error_msg = "找不到該用戶"
                    await ctx.send(util.format_error_msg(error_msg))
                    BotLogger.command_used(
                        "cc", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"錯誤: {error_msg}")
                    return

        if user is None:
            error_msg = "找不到該用戶，請確認輸入是否正確"
            await ctx.send(util.format_error_msg(error_msg))
            BotLogger.command_used(
                "cc", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"錯誤: {error_msg}")
            return

        # 創建切換式View
        view = CopycatToggleView(user, ctx.guild, self.bot, ctx.author.id)
        embed = await view.create_embed()
        
        message = await ctx.send(embed=embed, view=view)
        view.message = message

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
            # 創建切換式View
            view = CopycatToggleView(user, interaction.guild, self.bot, interaction.user.id)
            embed = await view.create_embed()
            
            await interaction.response.send_message(embed=embed, view=view)
            
            # 取得訊息reference
            message = await interaction.original_response()
            view.message = message
            
            # 記錄成功的指令使用
            BotLogger.command_used(
                "copycat",
                interaction.user.id,
                interaction.guild.id if interaction.guild else 0,
                f"目標用戶: {user.display_name} ({user.id})"
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
