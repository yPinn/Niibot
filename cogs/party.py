"""
簡化重構的分隊系統
使用模組化架構，大幅減少複雜度
"""

import asyncio
import random
import discord
from discord.ext import commands
from discord.ui import Modal, Select, TextInput, View

from utils.logger import BotLogger
from utils.util import read_json
from .party_modules import TeamDivider, PartyStateManager, VoiceChannelManager


class TeamSetupModal(Modal):
    """分隊設定對話框"""
    
    def __init__(self, party_cog, teams_value="2", players_value="auto"):
        super().__init__(title="分隊設定")
        self.party_cog = party_cog

        self.teams_input = TextInput(
            label="隊伍數量",
            placeholder="輸入隊伍數量 (例: 2)",
            default=teams_value,
            max_length=2
        )
        self.players_input = TextInput(
            label="每隊人數",
            placeholder="輸入每隊人數 (例: 4) 或 'auto'",
            default=players_value,
            max_length=10
        )
        
        self.add_item(self.teams_input)
        self.add_item(self.players_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.party_cog.handle_team_setup(interaction, self.teams_input.value, self.players_input.value)


class InviteView(View):
    """隊列邀請界面"""
    
    def __init__(self, party_cog, guild_id: int):
        super().__init__(timeout=None)  # 不設置超時，只有手動結束才移除按鈕
        self.party_cog = party_cog
        self.guild_id = guild_id

    @discord.ui.button(label="🎮 加入隊列", style=discord.ButtonStyle.primary)
    async def join_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.party_cog.handle_join_queue(interaction)

    @discord.ui.button(label="❌ 離開隊列", style=discord.ButtonStyle.secondary)
    async def leave_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.party_cog.handle_leave_queue(interaction)

    @discord.ui.button(label="⚡ 開始分隊", style=discord.ButtonStyle.success)
    async def start_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = TeamSetupModal(self.party_cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🗑️ 結束隊列", style=discord.ButtonStyle.danger)
    async def end_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.party_cog.handle_end_queue(interaction)

    async def on_timeout(self):
        # 不設置超時，此方法不會被調用
        pass


class TeamsManageView(View):
    """分隊後的管理界面"""
    
    def __init__(self, party_cog, guild_id: int):
        super().__init__(timeout=None)  # 不設置超時，由用戶主動控制
        self.party_cog = party_cog
        self.guild_id = guild_id

    @discord.ui.button(label="🔄 重新分隊", style=discord.ButtonStyle.primary)
    async def reshuffle_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.party_cog.handle_reshuffle(interaction)

    @discord.ui.button(label="🔊 語音分配", style=discord.ButtonStyle.secondary)
    async def voice_operations(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.party_cog.handle_voice_operations_manual(interaction)

    @discord.ui.button(label="🏁 結束並清理", style=discord.ButtonStyle.danger)
    async def end_and_cleanup(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.party_cog.handle_end_with_cleanup(interaction)

    async def on_timeout(self):
        # 不設置超時，此方法不會被調用
        pass


class Party(commands.Cog):
    """簡化的分隊系統"""
    
    def __init__(self, bot):
        self.bot = bot
        self.state_manager = PartyStateManager()
        self.voice_manager = VoiceChannelManager(bot)
        BotLogger.info("Party", "Party cog 初始化完成")
    
    def _can_manage_queue(self, guild_state, user: discord.Member) -> bool:
        """檢查用戶是否可以管理隊列（創建者或管理員）"""
        # 檢查是否為隊列創建者
        if guild_state.is_queue_creator(user.id):
            return True
        
        # 檢查是否為管理員（有管理伺服器權限）
        if user.guild_permissions.manage_guild:
            return True
        
        # 檢查是否有管理頻道權限
        if user.guild_permissions.manage_channels:
            return True
            
        return False
    
    def _bot_has_voice_permissions(self, guild: discord.Guild) -> tuple[bool, str]:
        """檢查機器人是否有語音頻道操作權限"""
        bot_member = guild.me
        missing_perms = []
        
        if not bot_member.guild_permissions.manage_channels:
            missing_perms.append("管理頻道")
        if not bot_member.guild_permissions.move_members:
            missing_perms.append("移動成員")
            
        if missing_perms:
            return False, f"權限不足：{', '.join(missing_perms)}"
        return True, "權限檢查通過"

    async def cog_unload(self):
        """清理資源"""
        # 取消所有清理任務
        active_guilds = await self.state_manager.get_all_active_guilds()
        for guild_id in active_guilds:
            self.voice_manager.cancel_cleanup(guild_id)
            await self.state_manager.cleanup_guild(guild_id)

    @commands.command(name="queue", aliases=["q", "開隊"], help="建立分隊隊列")
    async def queue(self, ctx: commands.Context, max_players: int = None):
        """建立分隊隊列"""
        guild_state = await self.state_manager.get_state(ctx.guild.id)
        
        async with guild_state.lock:
            # 檢查是否已有活躍隊列
            if await self.state_manager.has_active_queue(ctx.guild.id):
                await ctx.send("❌ 已有活躍的隊列，請先結束現有隊列")
                return
            
            # 檢查是否有未清理的原始訊息（額外的安全檢查）
            if guild_state.original_message:
                try:
                    # 嘗試檢查訊息是否仍然存在
                    await guild_state.original_message.fetch()
                    await ctx.send("❌ 已有活躍的隊列，請先結束現有隊列")
                    return
                except discord.NotFound:
                    # 訊息已被刪除，清理狀態
                    BotLogger.info("Party", "檢測到孤立的隊列狀態，自動清理")
                    await guild_state.cleanup_state()
                except:
                    # 其他錯誤，為了安全起見也清理狀態
                    await guild_state.cleanup_state()
            
            # 設定隊列
            guild_state.max_players = max_players
            guild_state.queue_creator = ctx.author.id
            
            # 記錄創建者的語音頻道
            if ctx.author.voice and ctx.author.voice.channel:
                guild_state.original_voice_channel = ctx.author.voice.channel
            
            # 創建邀請界面
            view = InviteView(self, ctx.guild.id)
            guild_state.active_views.add(view)
            
            embed = discord.Embed(
                title="🎮 分隊隊列",
                description="點擊下方按鈕加入隊列！\n✨ 分隊結果會@所有人，請注意通知\n⏰ 隊列將持續到Host手動結束",
                color=discord.Color.blue()
            )
            embed.add_field(name="👑 Host", value=ctx.author.mention, inline=True)
            embed.add_field(name="👥 玩家數", value="0", inline=True)
            
            if max_players:
                embed.add_field(name="📊 上限", value=str(max_players), inline=True)
            
            message = await ctx.send(embed=embed, view=view)
            # 記住原始訊息以便後續更新
            guild_state.original_message = message
            BotLogger.command_used("queue", ctx.author.id, ctx.guild.id, f"最大玩家: {max_players}")

    @commands.command(name="queue_reset", aliases=["qr", "清理隊列"], help="強制清理隊列狀態（管理員用）")
    @commands.has_permissions(manage_guild=True)
    async def queue_reset(self, ctx: commands.Context):
        """強制清理隊列狀態"""
        try:
            await self.state_manager.cleanup_guild(ctx.guild.id)
            await ctx.send("✅ 已強制清理隊列狀態，現在可以重新建立隊列")
            BotLogger.command_used("queue_reset", ctx.author.id, ctx.guild.id)
        except Exception as e:
            await ctx.send("❌ 清理狀態時發生錯誤")
            BotLogger.error("Party", f"強制清理狀態失敗: {e}", e)

    async def handle_join_queue(self, interaction: discord.Interaction):
        """處理加入隊列"""
        guild_state = await self.state_manager.get_state(interaction.guild.id)
        
        async with guild_state.lock:
            user_id = interaction.user.id
            
            # 檢查是否已在隊列中
            if guild_state.is_player_in_lobby(user_id):
                await interaction.response.send_message("⚠️ 你已經在隊列中了！", ephemeral=True)
                return
            
            # 嘗試加入隊列
            if guild_state.add_player(user_id, interaction.user.display_name):
                # 先回應interaction，然後更新原始訊息
                await interaction.response.send_message("✅ 成功加入隊列！", ephemeral=True)
                # 更新原始的隊列embed
                await self._update_original_queue_message(interaction, guild_state)
                BotLogger.user_action("加入隊列", user_id, interaction.guild.id, interaction.user.display_name)
            else:
                await interaction.response.send_message("❌ 隊列已滿！", ephemeral=True)

    async def handle_leave_queue(self, interaction: discord.Interaction):
        """處理離開隊列"""
        guild_state = await self.state_manager.get_state(interaction.guild.id)
        
        async with guild_state.lock:
            user_id = interaction.user.id
            
            if guild_state.remove_player(user_id):
                await interaction.response.send_message("✅ 已離開隊列！", ephemeral=True)
                # 更新原始的隊列embed
                await self._update_original_queue_message(interaction, guild_state)
                BotLogger.user_action("離開隊列", user_id, interaction.guild.id, interaction.user.display_name)
            else:
                await interaction.response.send_message("⚠️ 你不在隊列中！", ephemeral=True)

    async def handle_team_setup(self, interaction: discord.Interaction, teams_str: str, players_str: str):
        """處理分隊設定"""
        guild_state = await self.state_manager.get_state(interaction.guild.id)
        
        async with guild_state.lock:
            # 權限檢查
            if not self._can_manage_queue(guild_state, interaction.user):
                await interaction.response.send_message("❌ 只有隊列創建者或管理員可以開始分隊！", ephemeral=True)
                return
            
            # 語音權限檢查已移除，分隊功能可獨立運作
            
            total_players = guild_state.get_player_count()
            if total_players < 2:
                await interaction.response.send_message("❌ 至少需要2名玩家才能分隊！", ephemeral=True)
                return
            
            # 解析參數
            try:
                teams = int(teams_str)
                players_per_team = None if players_str.lower() == "auto" else int(players_str)
            except ValueError:
                await interaction.response.send_message("❌ 請輸入有效的數字！", ephemeral=True)
                return
            
            # 計算最佳分隊配置
            teams, players_per_team = TeamDivider.calculate_optimal_teams(total_players, teams, players_per_team)
            
            # 驗證配置
            is_valid, error_msg = TeamDivider.validate_team_config(total_players, teams, players_per_team)
            if not is_valid:
                await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
                return
            
            # 儲存分隊設定
            guild_state.team_settings = {
                'teams': teams,
                'players_per_team': players_per_team
            }
            
            # 執行分隊
            player_ids = guild_state.get_player_ids()
            team_lists = TeamDivider.divide_players(player_ids, teams, players_per_team)
            guild_state.set_teams(team_lists)
            
            # 顯示結果（公開訊息）並添加管理按鈕
            embed = await self._create_team_result_embed(guild_state, team_lists, interaction.guild, operator=interaction.user)
            teams_view = TeamsManageView(self, interaction.guild.id)
            guild_state.active_views.add(teams_view)
            await interaction.response.send_message(embed=embed, view=teams_view, ephemeral=False)
            
            # 保存分隊結果訊息引用
            team_message = await interaction.original_response()
            guild_state.team_result_messages.append(team_message)
            
            BotLogger.command_used("分隊", interaction.user.id, interaction.guild.id, 
                                 f"{teams}隊，每隊{players_per_team}人")

    async def handle_reshuffle(self, interaction: discord.Interaction):
        """處理重新分隊"""
        guild_state = await self.state_manager.get_state(interaction.guild.id)
        
        async with guild_state.lock:
            # 權限檢查
            if not self._can_manage_queue(guild_state, interaction.user):
                await interaction.response.send_message("❌ 只有隊列創建者或管理員可以重新分隊！", ephemeral=True)
                return
            
            if not guild_state.has_teams():
                await interaction.response.send_message("❌ 尚未進行過分隊！", ephemeral=True)
                return
            
            # 使用之前的設定重新分隊
            settings = guild_state.team_settings
            if not settings:
                await interaction.response.send_message("❌ 找不到分隊設定！", ephemeral=True)
                return
            
            player_ids = guild_state.get_player_ids()
            team_lists = TeamDivider.divide_players(player_ids, settings['teams'], settings['players_per_team'])
            guild_state.set_teams(team_lists)
            
            # 顯示結果（公開訊息）並添加管理按鈕
            embed = await self._create_team_result_embed(guild_state, team_lists, interaction.guild, is_reshuffle=True, operator=interaction.user)
            teams_view = TeamsManageView(self, interaction.guild.id)
            guild_state.active_views.add(teams_view)
            await interaction.response.send_message(embed=embed, view=teams_view, ephemeral=False)
            
            # 保存分隊結果訊息引用
            team_message = await interaction.original_response()
            guild_state.team_result_messages.append(team_message)
            
            BotLogger.user_action("重新分隊", interaction.user.id, interaction.guild.id)

    async def handle_end_queue(self, interaction: discord.Interaction):
        """處理結束隊列"""
        guild_state = await self.state_manager.get_state(interaction.guild.id)
        
        async with guild_state.lock:
            # 權限檢查
            if not self._can_manage_queue(guild_state, interaction.user):
                await interaction.response.send_message("❌ 只有隊列創建者或管理員可以結束隊列！", ephemeral=True)
                return
            
            # 先回應用戶
            await interaction.response.send_message("✅ 隊列已結束！", ephemeral=True)
            
            # 禁用原始訊息的所有按鈕並更新embed
            await self._disable_queue_buttons_and_update(guild_state, interaction.guild)
            
            # 清理狀態
            await guild_state.cleanup_state()
            
            BotLogger.user_action("結束隊列", interaction.user.id, interaction.guild.id)

    async def handle_end_with_cleanup(self, interaction: discord.Interaction):
        """處理結束隊列並清理語音頻道"""
        guild_state = await self.state_manager.get_state(interaction.guild.id)
        
        async with guild_state.lock:
            # 權限檢查
            if not self._can_manage_queue(guild_state, interaction.user):
                await interaction.response.send_message("❌ 只有隊列創建者或管理員可以結束隊列！", ephemeral=True)
                return
            
            # 清理語音頻道和分類夾
            if guild_state.created_channels:
                try:
                    stats = await self.voice_manager.cleanup_all_team_resources(
                        interaction.guild.id, 
                        guild_state.created_channels
                    )
                    
                    cleanup_msg = []
                    if stats['members_moved'] > 0:
                        cleanup_msg.append(f"📤 移動 {stats['members_moved']} 名玩家")
                    if stats['channels_deleted'] > 0:
                        cleanup_msg.append(f"🧹 清理 {stats['channels_deleted']} 個語音頻道")
                    if stats['category_deleted'] > 0:
                        cleanup_msg.append(f"📁 清理臨時分類夾")
                    
                    if cleanup_msg:
                        await interaction.response.send_message(
                            f"✅ 隊列已結束\n{' | '.join(cleanup_msg)}", 
                            ephemeral=True
                        )
                    else:
                        await interaction.response.send_message("✅ 隊列已結束", ephemeral=True)
                        
                except Exception as e:
                    BotLogger.error("Party", f"清理語音頻道失敗: {e}", e)
                    await interaction.response.send_message("✅ 隊列已結束（清理時發生錯誤）", ephemeral=True)
            else:
                await interaction.response.send_message("✅ 隊列已結束", ephemeral=True)
            
            # 禁用原始訊息的所有按鈕並更新embed（在清理狀態前）
            await self._disable_queue_buttons_and_update(guild_state, interaction.guild)
            
            # 移除分隊結果的按鈕
            await self._disable_teams_manage_buttons(guild_state, interaction)
            
            # 清理狀態
            await guild_state.cleanup_state()
            
            BotLogger.user_action("結束隊列並清理", interaction.user.id, interaction.guild.id)

    async def handle_voice_operations_manual(self, interaction: discord.Interaction):
        """處理手動語音操作"""
        guild_state = await self.state_manager.get_state(interaction.guild.id)
        
        async with guild_state.lock:
            # 權限檢查
            if not self._can_manage_queue(guild_state, interaction.user):
                await interaction.response.send_message("❌ 只有隊列創建者或管理員可以執行語音操作！", ephemeral=True)
                return
            
            # 檢查是否已分隊
            if not guild_state.has_teams():
                await interaction.response.send_message("❌ 尚未進行分隊，無法執行語音操作！", ephemeral=True)
                return
            
            # 檢查機器人權限
            has_perms, perm_msg = self._bot_has_voice_permissions(interaction.guild)
            if not has_perms:
                await interaction.response.send_message(
                    f"❌ 機器人{perm_msg}，無法執行語音頻道操作", 
                    ephemeral=True
                )
                return
            
            # 如果已經創建過語音頻道，詢問是否要重新創建
            if guild_state.created_channels:
                await interaction.response.send_message(
                    "⚠️ 已經創建過語音頻道，請先清理舊頻道或使用「結束並清理」功能", 
                    ephemeral=True
                )
                return
            
            # 執行語音操作
            team_lists = guild_state.get_teams()
            try:
                await interaction.response.send_message("🔄 正在執行語音分配...", ephemeral=True)
                await self._handle_voice_operations(interaction, guild_state, team_lists)
                BotLogger.user_action("手動語音操作", interaction.user.id, interaction.guild.id)
            except Exception as e:
                BotLogger.error("Party", f"手動語音操作失敗: {e}", e)
                await interaction.followup.send("❌ 語音操作執行失敗", ephemeral=True)

    async def _update_original_queue_message(self, interaction: discord.Interaction, guild_state):
        """更新原始隊列訊息"""
        try:
            if not guild_state.original_message:
                BotLogger.warning("Party", "找不到原始訊息，無法更新")
                return
                
            embed = discord.Embed(
                title="🎮 分隊隊列",
                description="點擊下方按鈕加入隊列！\n✨ 分隊結果會@所有人，請注意通知\n⏰ 隊列將持續到Host手動結束",
                color=discord.Color.blue()
            )
            
            creator = self.bot.get_user(guild_state.queue_creator)
            embed.add_field(name="👑 Host", value=creator.mention if creator else "未知", inline=True)
            embed.add_field(name="👥 玩家數", value=str(guild_state.get_player_count()), inline=True)
            
            if guild_state.max_players:
                embed.add_field(name="📊 上限", value=str(guild_state.max_players), inline=True)
            
            if guild_state.get_player_count() > 0:
                # 使用mention而不是名稱，避免重複名稱問題
                player_mentions = []
                for user_id in guild_state.get_player_ids():
                    member = interaction.guild.get_member(user_id)
                    if member:
                        player_mentions.append(f"• {member.mention}")
                    else:
                        # 備用方案：顯示名稱
                        name = guild_state.lobby.get(user_id, "未知用戶")
                        player_mentions.append(f"• {name}")
                
                embed.add_field(name="👥 隊列中的玩家", value="\n".join(player_mentions), inline=False)
            
            # 更新原始訊息
            await guild_state.original_message.edit(embed=embed)
        except Exception as e:
            BotLogger.error("Party", f"更新原始隊列訊息失敗: {e}", e)

    async def _disable_queue_buttons_and_update(self, guild_state, guild: discord.Guild):
        """禁用隊列按鈕並更新embed"""
        try:
            if not guild_state.original_message:
                BotLogger.warning("Party", "找不到原始訊息，無法禁用按鈕")
                return
            
            # 創建已結束的embed
            embed = discord.Embed(
                title="🎮 分隊隊列 (已結束)",
                description="此隊列已由Host結束，如需重新分隊請建立新隊列",
                color=discord.Color.red()
            )
            
            creator = self.bot.get_user(guild_state.queue_creator)
            embed.add_field(name="👑 Host", value=creator.mention if creator else "未知", inline=True)
            embed.add_field(name="👥 最終玩家數", value=str(guild_state.get_player_count()), inline=True)
            
            if guild_state.max_players:
                embed.add_field(name="📊 設定上限", value=str(guild_state.max_players), inline=True)
            
            if guild_state.get_player_count() > 0:
                player_mentions = []
                for user_id in guild_state.get_player_ids():
                    member = guild.get_member(user_id)
                    if member:
                        player_mentions.append(f"• {member.mention}")
                    else:
                        name = guild_state.lobby.get(user_id, "未知用戶")
                        player_mentions.append(f"• {name}")
                
                embed.add_field(name="👥 參與玩家", value="\n".join(player_mentions), inline=False)
            
            embed.set_footer(text="隊列已結束")
            
            # 創建禁用的View
            disabled_view = InviteView(self, guild.id)
            for item in disabled_view.children:
                item.disabled = True
                # 更改結束按鈕的樣式和標籤
                if hasattr(item, 'label') and item.label == "🗑️ 結束隊列":
                    item.label = "✅ 已結束"
                    item.style = discord.ButtonStyle.secondary
            
            # 更新原始訊息
            await guild_state.original_message.edit(embed=embed, view=disabled_view)
            
        except Exception as e:
            BotLogger.error("Party", f"禁用按鈕失敗: {e}", e)

    async def _disable_teams_manage_buttons(self, guild_state, interaction: discord.Interaction):
        """移除分隊管理按鈕，僅保留 embed"""
        try:
            # 更新所有分隊結果訊息，移除所有按鈕
            for team_message in guild_state.team_result_messages:
                try:
                    # 直接移除 view，僅保留 embed
                    await team_message.edit(view=None)
                    BotLogger.debug("Party", f"已移除分隊結果訊息的所有按鈕")
                    
                except discord.NotFound:
                    BotLogger.warning("Party", "分隊結果訊息已被刪除，跳過更新")
                except Exception as e:
                    BotLogger.warning("Party", f"移除分隊結果按鈕失敗: {e}")
            
            # 停用原有的活躍 Views
            for view in guild_state.active_views.copy():
                if isinstance(view, TeamsManageView):
                    view.stop()
                    
            BotLogger.debug("Party", "已移除所有分隊管理按鈕")
            
        except Exception as e:
            BotLogger.error("Party", f"移除分隊管理按鈕失敗: {e}", e)

    async def _create_team_result_embed(self, guild_state, team_lists, guild, is_reshuffle=False, operator=None):
        """創建分隊結果嵌入"""
        title = "⚡ 重新分隊結果" if is_reshuffle else "⚡ 分隊結果"
        embed = discord.Embed(title=title, color=discord.Color.green())
        
        # 添加操作者資訊
        if operator:
            embed.set_footer(text=f"由 {operator.display_name} 執行分隊", icon_url=operator.display_avatar.url)
        
        for i, team in enumerate(team_lists):
            team_members = []
            for user_id in team:
                member = guild.get_member(user_id)
                if member:
                    team_members.append(f"• {member.mention}")
                else:
                    # 備用方案：顯示名稱
                    name = guild_state.lobby.get(user_id, "未知用戶")
                    team_members.append(f"• {name}")
            
            embed.add_field(
                name=f"🔥 Team {i + 1}",
                value="\n".join(team_members),
                inline=True
            )
        
        unused_players = TeamDivider.get_unused_players(
            guild_state.get_player_ids(),
            len(team_lists),
            len(team_lists[0]) if team_lists else 0
        )
        
        if unused_players:
            unused_mentions = []
            for user_id in unused_players:
                member = guild.get_member(user_id)
                if member:
                    unused_mentions.append(f"• {member.mention}")
                else:
                    # 備用方案：顯示名稱
                    name = guild_state.lobby.get(user_id, "未知用戶")
                    unused_mentions.append(f"• {name}")
            embed.add_field(name="⏸️ 候補", value="\n".join(unused_mentions), inline=False)
        
        return embed

    async def _handle_voice_operations(self, interaction: discord.Interaction, guild_state, team_lists):
        """處理語音頻道操作"""
        try:
            # 創建語音頻道
            category = await self.voice_manager.get_suitable_category(interaction.guild)
            channels = await self.voice_manager.create_team_channels(
                interaction.guild, len(team_lists), category
            )
            guild_state.created_channels = channels
            
            # 移動玩家
            stats = await self.voice_manager.move_players_to_teams(
                interaction.guild, team_lists, channels
            )
            
            # 實時監控已在 create_team_channels 中啟動，無需額外排程
            
            if stats['moved'] > 0:
                await interaction.followup.send(
                    f"🔊 已移動 {stats['moved']} 名玩家到對應語音頻道！",
                    ephemeral=True
                )
            
        except discord.Forbidden:
            await interaction.followup.send(
                "⚠️ 沒有語音頻道管理權限，請手動移動到對應頻道",
                ephemeral=True
            )
        except Exception as e:
            BotLogger.error("Party", f"語音操作失敗: {e}", e)
            await interaction.followup.send(
                "⚠️ 語音頻道操作失敗，請手動移動到對應頻道",
                ephemeral=True
            )

    @commands.command(name="games", aliases=["game", "遊戲"], help="顯示遊戲網站連結")
    async def show_games(self, ctx: commands.Context):
        """顯示遊戲網站連結"""
        try:
            data = await read_json("data/game.json")
            if not data:
                await ctx.send("❌ 找不到遊戲資料")
                return
            
            if "urls" not in data or not data["urls"]:
                await ctx.send("❌ 找不到遊戲連結")
                return
            
            embed = discord.Embed(title="🎮 遊戲網站連結", color=discord.Color.green())
            
            url_list = []
            for i, game in enumerate(data["urls"], 1):
                url_list.append(f"{i}. [{game['name']}]({game['url']})")
            
            embed.description = "\n".join(url_list)
            embed.set_footer(text="點擊連結直接前往遊戲網站")
            
            await ctx.send(embed=embed)
            BotLogger.command_used("games", ctx.author.id, ctx.guild.id if ctx.guild else 0, "遊戲連結")
                
        except Exception as e:
            await ctx.send(f"❌ 讀取遊戲資料失敗：{str(e)}")
            BotLogger.error("Party", f"games 指令錯誤: {e}")

    @commands.command(name="codenames", aliases=["代號", "cn"], help="CodeNames 主題詞彙")
    async def show_codenames(self, ctx: commands.Context, theme: str = None):
        """顯示 CodeNames 主題詞彙"""
        try:
            data = await read_json("data/game.json")
            if not data or "CodeNames" not in data:
                await ctx.send("❌ 找不到 CodeNames 資料")
                return
            
            if theme is None:
                # 顯示主題選單
                await self._show_codenames_menu(ctx, data)
            else:
                # 顯示指定主題
                await self._show_codenames_theme(ctx, data, theme)
                
        except Exception as e:
            await ctx.send(f"❌ 讀取 CodeNames 資料失敗：{str(e)}")
            BotLogger.error("Party", f"codenames 指令錯誤: {e}")

    @show_codenames.error
    async def show_codenames_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("💡 使用方法：\n`?codenames` - 查看所有主題\n`?codenames 遊戲` - 查看遊戲主題詞彙")
        else:
            BotLogger.error("Party", f"codenames 指令錯誤: {error}")

    async def _show_codenames_menu(self, ctx: commands.Context, data: dict):
        """顯示 CodeNames 主題選單"""
        if "CodeNames" not in data or "themes" not in data["CodeNames"]:
            await ctx.send("❌ 找不到 CodeNames 主題資料")
            return
        
        themes = data["CodeNames"]["themes"]
        embed = discord.Embed(title="🕵️ CodeNames 主題選單", color=discord.Color.purple())
        
        theme_list = []
        for i, theme in enumerate(themes, 1):
            word_count = len(theme["words"])
            theme_list.append(f"{i}. **{theme['topic']}** ({word_count} 個詞彙)")
        
        embed.description = "\n".join(theme_list)
        embed.add_field(
            name="💡 使用方法",
            value="輸入 `?codenames 主題名稱` 來查看該主題的詞彙\n例如：`?codenames 遊戲`",
            inline=False
        )
        
        await ctx.send(embed=embed)
        BotLogger.command_used("codenames", ctx.author.id, ctx.guild.id if ctx.guild else 0, "CodeNames選單")

    async def _show_codenames_theme(self, ctx: commands.Context, data: dict, theme_name: str):
        """顯示指定的 CodeNames 主題詞彙"""
        if "CodeNames" not in data or "themes" not in data["CodeNames"]:
            await ctx.send("❌ 找不到 CodeNames 主題資料")
            return
        
        # 尋找匹配的主題
        target_theme = None
        for theme in data["CodeNames"]["themes"]:
            if theme["topic"].lower() == theme_name.lower():
                target_theme = theme
                break
        
        if not target_theme:
            # 如果找不到完全匹配，顯示可用主題
            available_themes = [theme["topic"] for theme in data["CodeNames"]["themes"]]
            await ctx.send(f"❌ 找不到主題「{theme_name}」\n\n📋 可用主題：{', '.join(available_themes)}")
            return
        
        embed = discord.Embed(
            title=f"🕵️ CodeNames - {target_theme['topic']}主題",
            color=discord.Color.purple()
        )
        
        words = target_theme["words"]
        # 將詞彙分成多列顯示
        words_per_column = 8
        columns = [words[i:i+words_per_column] for i in range(0, len(words), words_per_column)]
        
        for i, column in enumerate(columns):
            column_name = f"詞彙 {i*words_per_column+1}-{min((i+1)*words_per_column, len(words))}"
            embed.add_field(
                name=column_name,
                value="\n".join([f"• {word}" for word in column]),
                inline=True
            )
        
        embed.set_footer(text=f"總共 {len(words)} 個詞彙")
        
        await ctx.send(embed=embed)
        BotLogger.command_used("codenames", ctx.author.id, ctx.guild.id if ctx.guild else 0, f"CodeNames-{target_theme['topic']}")


async def setup(bot):
    await bot.add_cog(Party(bot))
    BotLogger.system_event("Cog載入", "Party cog 已成功載入")