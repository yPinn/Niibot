"""
Tinder 配對系統
提供類似交友軟體的配對功能和中介聊天
"""

import datetime
import asyncio
from typing import Dict, List, Optional, Set, Any
import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput

from utils.util import format_datetime, format_error_msg, format_success_msg, normalize_text, read_json, write_json
from utils.logger import BotLogger


class TinderData:
    """Tinder 資料管理類"""
    
    def __init__(self):
        self.data_file = "data/tinder.json"
        self.data = {}
        
    async def load_data(self):
        """載入資料"""
        try:
            self.data = await read_json(self.data_file) or {
                "users": {},  # user_id -> profile data
                "queue": [],  # 配對佇列中的用戶
                "likes": {},  # user_id -> [liked_user_ids]
                "matches": {},  # user_id -> [matched_user_ids]
                "chats": {}  # match_id -> chat_data
            }
        except Exception as e:
            BotLogger.error("Tinder", f"載入資料失敗: {e}")
            self.data = {"users": {}, "queue": [], "likes": {}, "matches": {}, "chats": {}}
    
    async def save_data(self):
        """儲存資料"""
        try:
            await write_json(self.data_file, self.data)
        except Exception as e:
            BotLogger.error("Tinder", f"儲存資料失敗: {e}")
    
    def get_user_profile(self, user_id: int) -> Optional[Dict]:
        """取得用戶資料"""
        return self.data["users"].get(str(user_id))
    
    def set_user_profile(self, user_id: int, profile: Dict):
        """設定用戶資料"""
        self.data["users"][str(user_id)] = profile
    
    def add_to_queue(self, user_id: int):
        """加入配對佇列"""
        if user_id not in self.data["queue"]:
            self.data["queue"].append(user_id)
    
    def remove_from_queue(self, user_id: int):
        """從配對佇列移除"""
        if user_id in self.data["queue"]:
            self.data["queue"].remove(user_id)
    
    def is_in_queue(self, user_id: int) -> bool:
        """檢查是否在佇列中"""
        return user_id in self.data["queue"]
    
    def get_queue_candidates(self, user_id: int) -> List[int]:
        """取得配對候選人（排除自己和已經按過讚的）"""
        liked_users = set(self.data["likes"].get(str(user_id), []))
        return [uid for uid in self.data["queue"] if uid != user_id and uid not in liked_users]
    
    def add_like(self, user_id: int, target_id: int):
        """添加按讚記錄"""
        user_key = str(user_id)
        if user_key not in self.data["likes"]:
            self.data["likes"][user_key] = []
        if target_id not in self.data["likes"][user_key]:
            self.data["likes"][user_key].append(target_id)
    
    def check_mutual_like(self, user_id: int, target_id: int) -> bool:
        """檢查是否互相按讚（配對成功）"""
        user_likes = self.data["likes"].get(str(user_id), [])
        target_likes = self.data["likes"].get(str(target_id), [])
        return target_id in user_likes and user_id in target_likes
    
    def add_match(self, user_id: int, target_id: int):
        """添加配對記錄"""
        for uid in [user_id, target_id]:
            user_key = str(uid)
            if user_key not in self.data["matches"]:
                self.data["matches"][user_key] = []
            other_id = target_id if uid == user_id else user_id
            if other_id not in self.data["matches"][user_key]:
                self.data["matches"][user_key].append(other_id)


class ProfileSetupModal(Modal):
    """個人檔案設定對話框"""
    
    def __init__(self, tinder_cog):
        super().__init__(title="設定你的 Tinder 個人檔案")
        self.tinder_cog = tinder_cog
        
        self.bio_input = TextInput(
            label="個人簡介",
            placeholder="說說關於你自己的事情...",
            style=discord.TextStyle.paragraph,
            max_length=200,
            required=False
        )
        
        self.interests_input = TextInput(
            label="興趣愛好",
            placeholder="例如：遊戲、電影、音樂、運動...",
            max_length=100,
            required=False
        )
        
        self.add_item(self.bio_input)
        self.add_item(self.interests_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        await self.tinder_cog.handle_profile_setup(
            interaction, 
            self.bio_input.value, 
            self.interests_input.value
        )


class TinderCardView(View):
    """配對卡片界面"""
    
    def __init__(self, tinder_cog, target_user_id: int):
        super().__init__(timeout=300)  # 5分鐘超時
        self.tinder_cog = tinder_cog
        self.target_user_id = target_user_id
    
    @discord.ui.button(label="❌ Pass", style=discord.ButtonStyle.secondary, emoji="❌")
    async def pass_button(self, interaction: discord.Interaction, button: Button):
        await self.tinder_cog.handle_pass(interaction, self.target_user_id)
        self.stop()
    
    @discord.ui.button(label="💖 Like", style=discord.ButtonStyle.primary, emoji="💖")
    async def like_button(self, interaction: discord.Interaction, button: Button):
        await self.tinder_cog.handle_like(interaction, self.target_user_id)
        self.stop()
    
    async def on_timeout(self):
        # 超時時禁用所有按鈕
        for item in self.children:
            item.disabled = True


class TinderMenuView(View):
    """Tinder 主選單"""
    
    def __init__(self, tinder_cog):
        super().__init__(timeout=None)
        self.tinder_cog = tinder_cog
    
    @discord.ui.button(label="💘 開始配對", style=discord.ButtonStyle.primary, emoji="💘")
    async def start_matching(self, interaction: discord.Interaction, button: Button):
        await self.tinder_cog.handle_start_matching(interaction)
    
    @discord.ui.button(label="👤 個人檔案", style=discord.ButtonStyle.secondary, emoji="👤")
    async def view_profile(self, interaction: discord.Interaction, button: Button):
        await self.tinder_cog.handle_view_profile(interaction)
    
    @discord.ui.button(label="⚙️ 設定檔案", style=discord.ButtonStyle.secondary, emoji="⚙️")
    async def setup_profile(self, interaction: discord.Interaction, button: Button):
        modal = ProfileSetupModal(self.tinder_cog)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="💬 配對聊天", style=discord.ButtonStyle.success, emoji="💬")
    async def view_matches(self, interaction: discord.Interaction, button: Button):
        await self.tinder_cog.handle_view_matches(interaction)


class Tinder(commands.Cog):
    """Tinder 配對系統"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = TinderData()
        self.active_sessions: Dict[int, Any] = {}  # user_id -> session_data
        BotLogger.info("Tinder", "Tinder 系統初始化完成")
    
    async def cog_load(self):
        """載入 Cog 時執行"""
        await self.data.load_data()
    
    async def cog_unload(self):
        """卸載 Cog 時執行"""
        await self.data.save_data()
    
    @commands.command(name="tinder", aliases=["配對", "t"], help="開啟 Tinder 配對系統")
    async def tinder_main(self, ctx: commands.Context):
        """Tinder 主選單"""
        try:
            embed = discord.Embed(
                title="💕 Tinder 配對系統",
                description="歡迎來到 Discord Tinder！\n在這裡你可以認識新朋友並進行配對。",
                color=0xff6b6b,
                timestamp=datetime.datetime.now()
            )
            
            embed.add_field(
                name="📋 如何使用",
                value="1. 設定你的個人檔案\n2. 開始配對尋找有趣的人\n3. 互相按讚即可配對成功\n4. 配對後可以開始聊天！",
                inline=False
            )
            
            embed.set_author(
                name="Tinder",
                icon_url="https://logos-world.net/wp-content/uploads/2020/09/Tinder-Logo.png"
            )
            
            embed.set_footer(
                text=f"由 {ctx.author.display_name} 開啟",
                icon_url=ctx.author.display_avatar.url
            )
            
            view = TinderMenuView(self)
            await ctx.send(embed=embed, view=view)
            
            BotLogger.command_used("tinder", ctx.author.id, ctx.guild.id if ctx.guild else 0)
            
        except Exception as e:
            await ctx.send(format_error_msg(f"開啟 Tinder 時發生錯誤：{str(e)}"))
            BotLogger.error("Tinder", f"tinder 指令錯誤: {e}", e)
    
    async def handle_profile_setup(self, interaction: discord.Interaction, bio: str, interests: str):
        """處理個人檔案設定"""
        try:
            user = interaction.user
            profile = {
                "user_id": user.id,
                "username": user.display_name,
                "avatar": user.display_avatar.url,
                "bio": bio.strip() if bio else "這個人很神秘，什麼都沒有留下...",
                "interests": interests.strip() if interests else "保持神秘感",
                "created_at": datetime.datetime.now().isoformat(),
                "active": True
            }
            
            self.data.set_user_profile(user.id, profile)
            await self.data.save_data()
            
            await interaction.response.send_message(
                format_success_msg("✅ 個人檔案設定完成！現在你可以開始配對了。"),
                ephemeral=True
            )
            
            BotLogger.user_action("設定檔案", user.id, interaction.guild.id if interaction.guild else 0)
            
        except Exception as e:
            await interaction.response.send_message(
                format_error_msg(f"設定檔案時發生錯誤：{str(e)}"),
                ephemeral=True
            )
            BotLogger.error("Tinder", f"設定檔案錯誤: {e}", e)
    
    async def handle_view_profile(self, interaction: discord.Interaction):
        """查看自己的個人檔案"""
        try:
            profile = self.data.get_user_profile(interaction.user.id)
            if not profile:
                await interaction.response.send_message(
                    format_error_msg("❌ 你還沒有設定個人檔案，請先點擊「設定檔案」。"),
                    ephemeral=True
                )
                return
            
            embed = await self._create_profile_embed(profile, interaction.user)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                format_error_msg(f"查看檔案時發生錯誤：{str(e)}"),
                ephemeral=True
            )
            BotLogger.error("Tinder", f"查看檔案錯誤: {e}", e)
    
    async def handle_start_matching(self, interaction: discord.Interaction):
        """開始配對"""
        try:
            # 檢查是否有設定檔案
            profile = self.data.get_user_profile(interaction.user.id)
            if not profile:
                await interaction.response.send_message(
                    format_error_msg("❌ 請先設定你的個人檔案才能開始配對。"),
                    ephemeral=True
                )
                return
            
            # 加入配對佇列
            self.data.add_to_queue(interaction.user.id)
            
            # 尋找候選人
            candidates = self.data.get_queue_candidates(interaction.user.id)
            if not candidates:
                await interaction.response.send_message(
                    "🔍 目前沒有其他人在配對佇列中，請稍後再試！\n💡 邀請朋友一起使用 Tinder 吧！",
                    ephemeral=True
                )
                await self.data.save_data()
                return
            
            # 顯示第一個候選人
            target_id = candidates[0]
            await self._show_candidate_card(interaction, target_id)
            await self.data.save_data()
            
        except Exception as e:
            await interaction.response.send_message(
                format_error_msg(f"開始配對時發生錯誤：{str(e)}"),
                ephemeral=True
            )
            BotLogger.error("Tinder", f"開始配對錯誤: {e}", e)
    
    async def _show_candidate_card(self, interaction: discord.Interaction, target_id: int):
        """顯示候選人卡片"""
        try:
            target_profile = self.data.get_user_profile(target_id)
            if not target_profile:
                await interaction.response.send_message(
                    "❌ 找不到候選人資料",
                    ephemeral=True
                )
                return
            
            # 取得目標用戶物件
            target_user = self.bot.get_user(target_id)
            if not target_user:
                target_user = await self.bot.fetch_user(target_id)
            
            embed = await self._create_profile_embed(target_profile, target_user, is_candidate=True)
            view = TinderCardView(self, target_id)
            
            await interaction.response.send_message(
                "💘 **發現新的配對候選人！**",
                embed=embed,
                view=view,
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.response.send_message(
                format_error_msg(f"顯示候選人時發生錯誤：{str(e)}"),
                ephemeral=True
            )
            BotLogger.error("Tinder", f"顯示候選人錯誤: {e}", e)
    
    async def handle_like(self, interaction: discord.Interaction, target_id: int):
        """處理按讚"""
        try:
            user_id = interaction.user.id
            
            # 記錄按讚
            self.data.add_like(user_id, target_id)
            
            # 檢查是否配對成功
            if self.data.check_mutual_like(user_id, target_id):
                # 配對成功！
                self.data.add_match(user_id, target_id)
                await self._notify_match(interaction, target_id)
            else:
                await interaction.response.send_message(
                    "💖 已送出讚！如果對方也喜歡你，就會配對成功～",
                    ephemeral=True
                )
            
            await self.data.save_data()
            BotLogger.user_action("按讚", user_id, interaction.guild.id if interaction.guild else 0, f"目標: {target_id}")
            
        except Exception as e:
            await interaction.response.send_message(
                format_error_msg(f"按讚時發生錯誤：{str(e)}"),
                ephemeral=True
            )
            BotLogger.error("Tinder", f"按讚錯誤: {e}", e)
    
    async def handle_pass(self, interaction: discord.Interaction, target_id: int):
        """處理略過"""
        try:
            await interaction.response.send_message(
                "➡️ 已略過此用戶",
                ephemeral=True
            )
            
            BotLogger.user_action("略過", interaction.user.id, interaction.guild.id if interaction.guild else 0, f"目標: {target_id}")
            
        except Exception as e:
            await interaction.response.send_message(
                format_error_msg(f"略過時發生錯誤：{str(e)}"),
                ephemeral=True
            )
            BotLogger.error("Tinder", f"略過錯誤: {e}", e)
    
    async def _notify_match(self, interaction: discord.Interaction, target_id: int):
        """通知配對成功"""
        try:
            target_user = self.bot.get_user(target_id)
            if not target_user:
                target_user = await self.bot.fetch_user(target_id)
            
            embed = discord.Embed(
                title="🎉 配對成功！",
                description=f"你和 **{target_user.display_name}** 配對成功了！\n現在你們可以開始聊天了～",
                color=0x00ff00,
                timestamp=datetime.datetime.now()
            )
            
            embed.set_thumbnail(url=target_user.display_avatar.url)
            embed.add_field(
                name="💬 開始聊天",
                value="使用「配對聊天」功能開始你們的對話吧！",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # 也通知對方（如果對方在線上）
            try:
                dm_embed = discord.Embed(
                    title="🎉 新的配對！",
                    description=f"你和 **{interaction.user.display_name}** 配對成功了！",
                    color=0x00ff00
                )
                await target_user.send(embed=dm_embed)
            except:
                pass  # 如果無法發送私訊就忽略
            
        except Exception as e:
            BotLogger.error("Tinder", f"通知配對成功錯誤: {e}", e)
    
    async def handle_view_matches(self, interaction: discord.Interaction):
        """查看配對列表"""
        try:
            user_id = interaction.user.id
            matches = self.data.data["matches"].get(str(user_id), [])
            
            if not matches:
                await interaction.response.send_message(
                    "💔 你還沒有任何配對，快去開始配對吧！",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="💕 你的配對列表",
                description="點擊下方按鈕開始與配對對象聊天！",
                color=0xff69b4,
                timestamp=datetime.datetime.now()
            )
            
            # 顯示配對列表
            match_list = []
            for i, match_id in enumerate(matches[:5]):  # 最多顯示5個配對
                try:
                    match_user = self.bot.get_user(match_id)
                    if not match_user:
                        match_user = await self.bot.fetch_user(match_id)
                    match_list.append(f"{i+1}. **{match_user.display_name}**")
                except:
                    match_list.append(f"{i+1}. 未知用戶")
            
            if match_list:
                embed.add_field(
                    name="👥 配對對象",
                    value="\n".join(match_list),
                    inline=False
                )
            
            embed.add_field(
                name="💡 使用說明",
                value="• 使用 `?chat @用戶` 開始聊天\n• 聊天訊息會匿名傳遞\n• 輸入 `結束聊天` 結束對話",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                format_error_msg(f"查看配對時發生錯誤：{str(e)}"),
                ephemeral=True
            )
            BotLogger.error("Tinder", f"查看配對錯誤: {e}", e)
    
    async def _create_profile_embed(self, profile: Dict, user: discord.User, is_candidate: bool = False) -> discord.Embed:
        """創建個人檔案 embed"""
        title = f"💖 {profile['username']}" if is_candidate else f"👤 {profile['username']} 的檔案"
        
        embed = discord.Embed(
            title=title,
            description=profile['bio'],
            color=0xff6b6b,
            timestamp=datetime.datetime.now()
        )
        
        embed.set_image(url=profile['avatar'])
        embed.add_field(name="🎯 興趣", value=profile['interests'], inline=False)
        
        if not is_candidate:
            created_date = datetime.datetime.fromisoformat(profile['created_at'])
            embed.add_field(
                name="📅 加入時間",
                value=format_datetime(created_date),
                inline=True
            )
        
        embed.set_footer(
            text="Tinder 配對系統",
            icon_url="https://logos-world.net/wp-content/uploads/2020/09/Tinder-Logo.png"
        )
        
        return embed
    
    def wrap_text(self, text: str, line_length: int) -> str:
        """文字換行"""
        return '\n'.join([
            text[i:i + line_length] for i in range(0, len(text), line_length)
        ])
    
    @commands.command(name="chat", aliases=["聊天"], help="與配對對象開始中介聊天")
    async def start_chat(self, ctx: commands.Context, target: discord.Member = None):
        """開始與配對對象的中介聊天"""
        try:
            if not target:
                await ctx.send(format_error_msg("❌ 請指定要聊天的配對對象！\n使用方法：`?chat @用戶`"))
                return
            
            user_id = ctx.author.id
            target_id = target.id
            
            # 檢查是否為配對關係
            matches = self.data.data["matches"].get(str(user_id), [])
            if target_id not in matches:
                await ctx.send(format_error_msg("❌ 你們還沒有配對，無法開始聊天！"))
                return
            
            # 建立聊天會話
            chat_id = f"{min(user_id, target_id)}_{max(user_id, target_id)}"
            
            # 初始化聊天記錄
            if chat_id not in self.data.data["chats"]:
                self.data.data["chats"][chat_id] = {
                    "participants": [user_id, target_id],
                    "messages": [],
                    "created_at": datetime.datetime.now().isoformat(),
                    "active": True
                }
            
            # 設定聊天會話
            self.active_sessions[user_id] = {
                "chat_id": chat_id,
                "target_id": target_id,
                "started_at": datetime.datetime.now()
            }
            
            embed = discord.Embed(
                title="💬 聊天開始",
                description=f"你現在正在與 **{target.display_name}** 聊天！",
                color=0x00ff9f,
                timestamp=datetime.datetime.now()
            )
            
            embed.add_field(
                name="📝 使用說明",
                value="• 直接發送訊息即可傳遞給對方\n• 輸入 `結束聊天` 結束對話\n• 訊息會匿名傳遞",
                inline=False
            )
            
            embed.set_footer(text="Tinder 中介聊天系統")
            
            await ctx.send(embed=embed)
            await self.data.save_data()
            
            BotLogger.user_action("開始聊天", user_id, ctx.guild.id if ctx.guild else 0, f"目標: {target_id}")
            
        except Exception as e:
            await ctx.send(format_error_msg(f"開始聊天時發生錯誤：{str(e)}"))
            BotLogger.error("Tinder", f"開始聊天錯誤: {e}", e)
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """監聽訊息，處理中介聊天"""
        try:
            # 忽略機器人訊息
            if message.author.bot:
                return
            
            # 檢查是否在聊天會話中
            user_id = message.author.id
            if user_id not in self.active_sessions:
                return
            
            # 檢查是否為結束聊天指令
            if message.content.strip() in ["結束聊天", "end chat", "quit"]:
                await self._end_chat_session(message)
                return
            
            # 忽略指令訊息
            if message.content.startswith(('?', '!', '/', '$')):
                return
            
            session = self.active_sessions[user_id]
            chat_id = session["chat_id"]
            target_id = session["target_id"]
            
            # 取得目標用戶
            target_user = self.bot.get_user(target_id)
            if not target_user:
                target_user = await self.bot.fetch_user(target_id)
            
            # 記錄訊息
            message_data = {
                "sender_id": user_id,
                "content": message.content,
                "timestamp": datetime.datetime.now().isoformat()
            }
            
            if chat_id in self.data.data["chats"]:
                self.data.data["chats"][chat_id]["messages"].append(message_data)
                await self.data.save_data()
            
            # 傳遞訊息給配對對象
            embed = discord.Embed(
                title="💕 配對對象的訊息",
                description=message.content,
                color=0xff69b4,
                timestamp=datetime.datetime.now()
            )
            
            embed.set_footer(text="回覆訊息只需直接發送訊息即可 • 輸入「結束聊天」結束對話")
            
            try:
                await target_user.send(embed=embed)
            except discord.Forbidden:
                # 如果無法發送私訊，在原頻道提醒
                await message.channel.send(
                    f"⚠️ 無法發送私訊給 **{target_user.display_name}**，請確認對方開啟私訊功能。"
                )
            
            # 給發送者確認
            await message.add_reaction("💕")
            
            BotLogger.user_action("發送聊天訊息", user_id, message.guild.id if message.guild else 0)
            
        except Exception as e:
            BotLogger.error("Tinder", f"處理聊天訊息錯誤: {e}", e)
    
    async def _end_chat_session(self, message):
        """結束聊天會話"""
        try:
            user_id = message.author.id
            if user_id in self.active_sessions:
                session = self.active_sessions[user_id]
                target_id = session["target_id"]
                
                # 移除會話
                del self.active_sessions[user_id]
                
                # 通知結束
                embed = discord.Embed(
                    title="💔 聊天結束",
                    description="聊天會話已結束。",
                    color=0x999999,
                    timestamp=datetime.datetime.now()
                )
                
                await message.channel.send(embed=embed)
                
                # 通知對方
                try:
                    target_user = self.bot.get_user(target_id)
                    if not target_user:
                        target_user = await self.bot.fetch_user(target_id)
                    
                    end_embed = discord.Embed(
                        title="💔 聊天結束",
                        description="對方結束了聊天會話。",
                        color=0x999999
                    )
                    await target_user.send(embed=end_embed)
                except:
                    pass
                
                BotLogger.user_action("結束聊天", user_id, message.guild.id if message.guild else 0)
            
        except Exception as e:
            BotLogger.error("Tinder", f"結束聊天錯誤: {e}", e)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tinder(bot))
    BotLogger.system_event("Cog載入", "Tinder cog 已成功載入")