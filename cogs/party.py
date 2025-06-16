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
        super().__init__(timeout=300)  # 5分鐘超時
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

    @discord.ui.button(label="🔄 重新分隊", style=discord.ButtonStyle.danger)
    async def reshuffle_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.party_cog.handle_reshuffle(interaction)

    @discord.ui.button(label="🗑️ 結束隊列", style=discord.ButtonStyle.danger)
    async def end_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.party_cog.handle_end_queue(interaction)

    async def on_timeout(self):
        # 超時時禁用所有按鈕
        for item in self.children:
            item.disabled = True


class Party(commands.Cog):
    """簡化的分隊系統"""
    
    def __init__(self, bot):
        self.bot = bot
        self.state_manager = PartyStateManager()
        self.voice_manager = VoiceChannelManager(bot)
        BotLogger.info("Party", "Party cog 初始化完成")

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
            if guild_state.get_player_count() > 0:
                await ctx.send("❌ 已有活躍的隊列，請先結束現有隊列")
                return
            
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
                description="點擊下方按鈕加入隊列！",
                color=discord.Color.blue()
            )
            embed.add_field(name="👑 隊長", value=ctx.author.mention, inline=True)
            embed.add_field(name="👥 玩家數", value="0", inline=True)
            
            if max_players:
                embed.add_field(name="📊 上限", value=str(max_players), inline=True)
            
            await ctx.send(embed=embed, view=view)
            BotLogger.command_used("queue", ctx.author.id, ctx.guild.id, f"最大玩家: {max_players}")

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
                await interaction.response.send_message("✅ 成功加入隊列！", ephemeral=True)
                await self._update_queue_display(interaction, guild_state)
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
                await self._update_queue_display(interaction, guild_state)
                BotLogger.user_action("離開隊列", user_id, interaction.guild.id, interaction.user.display_name)
            else:
                await interaction.response.send_message("⚠️ 你不在隊列中！", ephemeral=True)

    async def handle_team_setup(self, interaction: discord.Interaction, teams_str: str, players_str: str):
        """處理分隊設定"""
        guild_state = await self.state_manager.get_state(interaction.guild.id)
        
        async with guild_state.lock:
            # 權限檢查
            if not guild_state.is_queue_creator(interaction.user.id):
                await interaction.response.send_message("❌ 只有隊列創建者可以開始分隊！", ephemeral=True)
                return
            
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
            
            # 執行分隊
            player_ids = guild_state.get_player_ids()
            team_lists = TeamDivider.divide_players(player_ids, teams, players_per_team)
            guild_state.set_teams(team_lists)
            
            # 顯示結果
            embed = await self._create_team_result_embed(guild_state, team_lists, interaction.guild)
            await interaction.response.send_message(embed=embed)
            
            # 嘗試語音頻道操作
            await self._handle_voice_operations(interaction, guild_state, team_lists)
            
            BotLogger.command_used("分隊", interaction.user.id, interaction.guild.id, 
                                 f"{teams}隊，每隊{players_per_team}人")

    async def handle_reshuffle(self, interaction: discord.Interaction):
        """處理重新分隊"""
        guild_state = await self.state_manager.get_state(interaction.guild.id)
        
        async with guild_state.lock:
            # 權限檢查
            if not guild_state.is_queue_creator(interaction.user.id):
                await interaction.response.send_message("❌ 只有隊列創建者可以重新分隊！", ephemeral=True)
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
            
            # 顯示結果
            embed = await self._create_team_result_embed(guild_state, team_lists, interaction.guild, is_reshuffle=True)
            await interaction.response.send_message(embed=embed)
            
            # 嘗試語音頻道操作
            await self._handle_voice_operations(interaction, guild_state, team_lists)
            
            BotLogger.user_action("重新分隊", interaction.user.id, interaction.guild.id)

    async def handle_end_queue(self, interaction: discord.Interaction):
        """處理結束隊列"""
        guild_state = await self.state_manager.get_state(interaction.guild.id)
        
        async with guild_state.lock:
            # 權限檢查
            if not guild_state.is_queue_creator(interaction.user.id):
                await interaction.response.send_message("❌ 只有隊列創建者可以結束隊列！", ephemeral=True)
                return
            
            await guild_state.cleanup_state()
            await interaction.response.send_message("✅ 隊列已結束！")
            
            BotLogger.user_action("結束隊列", interaction.user.id, interaction.guild.id)

    async def _update_queue_display(self, interaction: discord.Interaction, guild_state):
        """更新隊列顯示"""
        try:
            embed = discord.Embed(
                title="🎮 分隊隊列",
                description="點擊下方按鈕加入隊列！",
                color=discord.Color.blue()
            )
            
            creator = self.bot.get_user(guild_state.queue_creator)
            embed.add_field(name="👑 隊長", value=creator.mention if creator else "未知", inline=True)
            embed.add_field(name="👥 玩家數", value=str(guild_state.get_player_count()), inline=True)
            
            if guild_state.max_players:
                embed.add_field(name="📊 上限", value=str(guild_state.max_players), inline=True)
            
            if guild_state.get_player_count() > 0:
                player_list = "\n".join([f"• {name}" for name in guild_state.get_player_list()])
                embed.add_field(name="👥 隊列中的玩家", value=player_list, inline=False)
            
            await interaction.edit_original_response(embed=embed)
        except Exception as e:
            BotLogger.error("Party", f"更新隊列顯示失敗: {e}", e)

    async def _create_team_result_embed(self, guild_state, team_lists, guild, is_reshuffle=False):
        """創建分隊結果嵌入"""
        title = "⚡ 重新分隊結果" if is_reshuffle else "⚡ 分隊結果"
        embed = discord.Embed(title=title, color=discord.Color.green())
        
        for i, team in enumerate(team_lists):
            team_members = []
            for user_id in team:
                member = guild.get_member(user_id)
                name = member.display_name if member else guild_state.lobby.get(user_id, "未知")
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
            unused_names = []
            for user_id in unused_players:
                member = guild.get_member(user_id)
                name = member.display_name if member else guild_state.lobby.get(user_id, "未知")
                unused_names.append(f"• {name}")
            embed.add_field(name="⏸️ 候補", value="\n".join(unused_names), inline=False)
        
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
            
            # 排程清理
            await self.voice_manager.schedule_cleanup(interaction.guild.id, channels)
            
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

    @commands.command(name="games", aliases=["game", "遊戲"], help="顯示遊戲清單")
    async def show_games(self, ctx: commands.Context):
        """顯示遊戲清單"""
        try:
            data = await read_json("data/game.json")
            if not data or "games" not in data:
                await ctx.send("❌ 找不到遊戲清單")
                return
            
            games = data["games"]
            if not games:
                await ctx.send("📝 遊戲清單是空的")
                return
            
            embed = discord.Embed(title="🎮 遊戲清單", color=discord.Color.blue())
            
            game_list = []
            for i, game in enumerate(games[:20], 1):  # 限制顯示20個
                game_list.append(f"{i}. {game}")
            
            embed.description = "\n".join(game_list)
            
            if len(games) > 20:
                embed.set_footer(text=f"顯示前 20 個，總共 {len(games)} 個遊戲")
            
            await ctx.send(embed=embed)
            BotLogger.command_used("games", ctx.author.id, ctx.guild.id if ctx.guild else 0)
            
        except Exception as e:
            await ctx.send("❌ 讀取遊戲清單失敗")
            BotLogger.error("Party", f"讀取遊戲清單失敗: {e}", e)


async def setup(bot):
    await bot.add_cog(Party(bot))
    BotLogger.system_event("Cog載入", "Party cog 已成功載入")