import asyncio
import os
import random

import discord
from discord.ext import commands
from discord.ui import Modal, Select, TextInput, View

from utils.util import read_json  # 假設是非同步版本

DATA_DIR = "data"
GAME_FILE = os.path.join(DATA_DIR, "game.json")


class TeamSetupModal(Modal):
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
            placeholder="輸入每隊人數 或 'auto' 自動分配",
            default=players_value,
            max_length=10
        )

        self.add_item(self.teams_input)
        self.add_item(self.players_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # 解析輸入
            teams_str = self.teams_input.value.strip()
            players_str = self.players_input.value.strip().lower()

            # 驗證隊伍數
            teams = int(teams_str)
            if teams < 1:
                await interaction.response.send_message("⚠️ 隊伍數必須至少為 1", ephemeral=True)
                return

            # 解析每隊人數
            if players_str == "auto":
                players_per_team = None
            else:
                players_per_team = int(players_str)
                if players_per_team < 1:
                    await interaction.response.send_message("⚠️ 每隊人數必須至少為 1", ephemeral=True)
                    return

            # 執行分隊
            await self.party_cog.execute_team_division(interaction, teams, players_per_team)

        except ValueError:
            await interaction.response.send_message("⚠️ 請輸入有效的數字", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"⚠️ 發生錯誤: {e}", ephemeral=True)


class TeamSetupSelect(View):
    def __init__(self, party_cog, total_players):
        super().__init__(timeout=300)
        self.party_cog = party_cog
        self.total_players = total_players
        self.teams = 2
        self.players_per_team = "auto"

    @discord.ui.select(
        placeholder="選擇隊伍數量",
        options=[
            discord.SelectOption(label="2 隊", value="2"),
            discord.SelectOption(label="3 隊", value="3"),
            discord.SelectOption(label="4 隊", value="4"),
            discord.SelectOption(label="5 隊", value="5"),
            discord.SelectOption(label="自訂", value="custom"),
        ]
    )
    async def select_teams(self, interaction: discord.Interaction, select: Select):
        if select.values[0] == "custom":
            modal = TeamSetupModal(self.party_cog, str(
                self.teams), str(self.players_per_team))
            await interaction.response.send_modal(modal)
        else:
            self.teams = int(select.values[0])
            await interaction.response.defer()

    @discord.ui.select(
        placeholder="選擇每隊人數",
        options=[
            discord.SelectOption(label="自動分配", value="auto"),
            discord.SelectOption(label="2 人", value="2"),
            discord.SelectOption(label="3 人", value="3"),
            discord.SelectOption(label="4 人", value="4"),
            discord.SelectOption(label="5 人", value="5"),
            discord.SelectOption(label="6 人", value="6"),
            discord.SelectOption(label="自訂", value="custom"),
        ]
    )
    async def select_players(self, interaction: discord.Interaction, select: Select):
        if select.values[0] == "custom":
            modal = TeamSetupModal(self.party_cog, str(
                self.teams), str(self.players_per_team))
            await interaction.response.send_modal(modal)
        else:
            self.players_per_team = None if select.values[0] == "auto" else int(
                select.values[0])
            await interaction.response.defer()

    @discord.ui.button(label="確認分隊", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.party_cog.execute_team_division(interaction, self.teams, self.players_per_team)

    @discord.ui.button(label="取消", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ 已取消分隊設定", view=None)


class InviteView(View):
    def __init__(self, party_cog, queue: dict, message: discord.Message = None, lock: asyncio.Lock = None,
                 max_players: int = None, queue_creator: int = None):
        super().__init__(timeout=None)
        self.party_cog = party_cog
        self.queue = queue
        self.message = message
        self.lock = lock
        self.max_players = max_players
        self.queue_creator = queue_creator

    def _check_permission(self, user: discord.Member) -> bool:
        """檢查用戶是否有權限操作"""
        return (user.id == self.queue_creator or
                user.guild_permissions.administrator)

    async def _check_voice_permissions(self, guild: discord.Guild) -> bool:
        """檢查機器人是否有語音頻道權限"""
        bot_member = guild.me
        return (bot_member.guild_permissions.manage_channels and
                bot_member.guild_permissions.move_members)

    @discord.ui.button(label="加入隊列", style=discord.ButtonStyle.success, custom_id="join_queue", emoji="✅")
    async def join_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        display_name = interaction.user.display_name

        if self.lock:
            async with self.lock:
                if user_id in self.queue:
                    await interaction.response.send_message("⚠️ 您已經在隊列中了！", ephemeral=True)
                    return

                if self.max_players and len(self.queue) >= self.max_players:
                    await interaction.response.send_message(f"⚠️ 隊列已滿 ({self.max_players}人)", ephemeral=True)
                    return

                self.queue[user_id] = display_name
                await self._update_queue_message()

        await interaction.response.send_message(f"✅ {interaction.user.mention} 已加入隊列", ephemeral=True)

    @discord.ui.button(label="離開隊列", style=discord.ButtonStyle.danger, custom_id="leave_queue", emoji="❌")
    async def leave_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id

        if self.lock:
            async with self.lock:
                if user_id not in self.queue:
                    await interaction.response.send_message("⚠️ 您不在隊列中！", ephemeral=True)
                    return

                self.queue.pop(user_id)
                await self._update_queue_message()

        await interaction.response.send_message(f"❌ {interaction.user.mention} 已離開隊列", ephemeral=True)

    @discord.ui.button(label="清空隊列", style=discord.ButtonStyle.secondary, custom_id="clear_queue", emoji="🗑️")
    async def clear_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check_permission(interaction.user):
            await interaction.response.send_message("⚠️ 您沒有權限清空隊列！", ephemeral=True)
            return

        if self.lock:
            async with self.lock:
                if not self.queue:
                    await interaction.response.send_message("⚠️ 隊列已經是空的！", ephemeral=True)
                    return

                self.queue.clear()
                # 重置分隊狀態
                self.party_cog.current_teams = []
                self.party_cog.team_settings = {}
                await self._update_queue_message()

        await interaction.response.send_message("🗑️ 隊列已清空！", ephemeral=True)

    @discord.ui.button(label="開始分隊", style=discord.ButtonStyle.primary, custom_id="start_team", emoji="⚡")
    async def start_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check_permission(interaction.user):
            await interaction.response.send_message("⚠️ 您沒有權限開始分隊！", ephemeral=True)
            return

        if len(self.queue) < 2:
            await interaction.response.send_message("⚠️ 隊列至少需要 2 人才能開始分隊", ephemeral=True)
            return

        # 創建分隊設定界面
        setup_view = TeamSetupSelect(self.party_cog, len(self.queue))
        await interaction.response.send_message("🎯 請選擇分隊設定：", view=setup_view, ephemeral=True)

    @discord.ui.button(label="重新分隊", style=discord.ButtonStyle.secondary, custom_id="reshuffle", emoji="🔄")
    async def reshuffle_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check_permission(interaction.user):
            await interaction.response.send_message("⚠️ 您沒有權限重新分隊！", ephemeral=True)
            return

        if not self.party_cog.current_teams or not self.party_cog.team_settings:
            await interaction.response.send_message("⚠️ 尚未進行過分隊！", ephemeral=True)
            return

        settings = self.party_cog.team_settings
        await self.party_cog.execute_team_division(
            interaction,
            settings['teams'],
            settings['players_per_team'],
            is_reshuffle=True
        )

    @discord.ui.button(label="重新設定", style=discord.ButtonStyle.secondary, custom_id="reconfig", emoji="⚙️")
    async def reconfigure_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check_permission(interaction.user):
            await interaction.response.send_message("⚠️ 您沒有權限重新設定！", ephemeral=True)
            return

        # 使用之前的設定作為預設值
        settings = self.party_cog.team_settings
        teams_default = str(settings.get('teams', 2))
        players_default = str(settings.get('players_per_team', 'auto'))

        modal = TeamSetupModal(self.party_cog, teams_default, players_default)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="移動到語音", style=discord.ButtonStyle.success, custom_id="move_voice", emoji="🔊")
    async def move_to_voice(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check_permission(interaction.user):
            await interaction.response.send_message("⚠️ 您沒有權限操作語音頻道！", ephemeral=True)
            return

        # 檢查語音權限
        if not await self._check_voice_permissions(interaction.guild):
            await interaction.response.send_message("⚠️ 機器人缺少語音頻道管理權限，無法移動玩家", ephemeral=True)
            return

        if not self.party_cog.current_teams:
            await interaction.response.send_message("⚠️ 尚未進行分隊！", ephemeral=True)
            return

        moved_count = await self.party_cog.move_players_to_voice(interaction.guild)
        await interaction.response.send_message(f"🔊 已移動 {moved_count} 名玩家到語音頻道", ephemeral=True)

    @discord.ui.button(label="拉回原頻道", style=discord.ButtonStyle.secondary, custom_id="return_voice", emoji="🏠")
    async def return_to_original(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check_permission(interaction.user):
            await interaction.response.send_message("⚠️ 您沒有權限操作語音頻道！", ephemeral=True)
            return

        # 檢查語音權限
        if not await self._check_voice_permissions(interaction.guild):
            await interaction.response.send_message("⚠️ 機器人缺少語音頻道管理權限，無法移動玩家", ephemeral=True)
            return

        if not self.party_cog.original_voice_channel:
            await interaction.response.send_message("⚠️ 找不到原始語音頻道！", ephemeral=True)
            return

        moved_count = await self.party_cog.return_players_to_original(interaction.guild)
        await interaction.response.send_message(f"🏠 已拉回 {moved_count} 名玩家到原頻道", ephemeral=True)

    async def _update_queue_message(self):
        """更新隊列顯示訊息"""
        if not self.message:
            return

        content = await self._generate_queue_content()

        # 檢查語音權限並動態更新按鈕狀態
        has_voice_perm = await self._check_voice_permissions(self.message.guild)
        self._update_button_states(has_voice_perm)

        try:
            await self.message.edit(content=content, view=self)
        except discord.NotFound:
            self.message = None

    def _update_button_states(self, has_voice_permission: bool):
        """根據權限和狀態更新按鈕"""
        has_teams = bool(self.party_cog.current_teams)

        # 找到對應的按鈕
        for item in self.children:
            if item.custom_id == "start_team":
                item.disabled = has_teams
            elif item.custom_id == "reshuffle":
                item.disabled = not has_teams
            elif item.custom_id == "reconfig":
                item.disabled = not has_teams
            elif item.custom_id == "move_voice":
                item.disabled = not has_teams or not has_voice_permission
            elif item.custom_id == "return_voice":
                item.disabled = not has_teams or not has_voice_permission

    async def _generate_queue_content(self) -> str:
        """生成隊列內容字符串"""
        # 隊列狀態
        queue_list = []
        team_member_ids = set()
        if self.party_cog.current_teams:
            for team in self.party_cog.current_teams:
                team_member_ids.update(team)

        for i, (uid, name) in enumerate(self.queue.items(), 1):
            if uid in team_member_ids:
                queue_list.append(f"{i}. {name} ※ 待下次分隊")
            else:
                queue_list.append(f"{i}. {name}")

        if not queue_list:
            queue_list = ["目前沒有人在隊列中"]

        # 基本信息
        max_text = f" / {self.max_players}" if self.max_players else ""
        limit_text = f" (上限: {self.max_players} 人)" if self.max_players else " (無上限)"

        content = f"🎮 **配對大廳** 🎮{limit_text}\n"
        content += f"[目前有 {len(self.queue)}{max_text} 人]"

        # 分隊結果
        if self.party_cog.current_teams:
            content += f" [已分隊: {len(self.party_cog.current_teams)} 隊]"

        content += f"\n\n**隊列成員：**\n" + "\n".join(queue_list)

        # 分隊結果顯示
        if self.party_cog.current_teams:
            content += f"\n\n**分隊結果：**\n"
            for i, team in enumerate(self.party_cog.current_teams, 1):
                team_names = []
                for uid in team:
                    member = self.message.guild.get_member(uid)
                    if member:
                        team_names.append(member.display_name)
                content += f"🔸 Team {i}: {', '.join(team_names)}\n"

        # 權限提示
        if self.party_cog.current_teams:
            has_voice_perm = await self._check_voice_permissions(self.message.guild)
            if not has_voice_perm:
                content += f"\n⚠️ **機器人缺少語音頻道管理權限**\n無法創建/移動語音頻道，請聯繫管理員"

        return content


class Party(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.lobby = {}  # dict user_id -> display_name
        self.lock = asyncio.Lock()
        self.max_players = None
        self.queue_creator = None
        self.original_voice_channel = None
        self.current_teams = []  # [[team1_ids], [team2_ids], ...]
        self.team_settings = {}  # {'teams': int, 'players_per_team': int/None}
        self.cleanup_task = self.bot.loop.create_task(
            self.cleanup_empty_voice_channels())

    def cog_unload(self):
        self.cleanup_task.cancel()

    async def cleanup_empty_voice_channels(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            for guild in self.bot.guilds:
                for channel in guild.voice_channels:
                    if channel.name.startswith("team-") and len(channel.members) == 0:
                        try:
                            await channel.delete()
                            print(f"自動刪除空語音頻道：{channel.name}")
                        except Exception as e:
                            print(f"刪除語音頻道失敗: {e}")
            await asyncio.sleep(60)

    def _get_original_voice_channel(self, ctx: commands.Context):
        """獲取原始語音頻道"""
        if ctx.author.voice and ctx.author.voice.channel:
            return ctx.author.voice.channel

        # 找人數最多的非team-頻道
        guild = ctx.guild
        valid_channels = [
            ch for ch in guild.voice_channels
            if not ch.name.startswith("team-") and len(ch.members) > 0
        ]

        if valid_channels:
            # 按人數排序，人數相同時按字母順序
            return max(valid_channels, key=lambda c: (len(c.members), -ord(c.name[0].lower())))

        return None

    @commands.command(name="queue", aliases=["q"], help="分隊大廳 - 用法: !queue [人數上限]")
    async def queue(self, ctx: commands.Context, max_players: int = None):
        if max_players is not None and max_players <= 0:
            await ctx.send("⚠️ 人數上限必須大於 0！")
            return

        # 記錄隊列創建者和原始語音頻道
        self.queue_creator = ctx.author.id
        self.original_voice_channel = self._get_original_voice_channel(ctx)
        self.max_players = max_players

        # 處理現有隊列超過上限的情況
        if max_players and len(self.lobby) > max_players:
            await ctx.send(f"⚠️ 當前隊列有 {len(self.lobby)} 人，超過設定上限 {max_players} 人。將保留前 {max_players} 名玩家。")
            lobby_items = list(self.lobby.items())[:max_players]
            self.lobby = dict(lobby_items)

        view = InviteView(
            self, self.lobby, lock=self.lock,
            max_players=max_players, queue_creator=self.queue_creator
        )

        content = await view._generate_queue_content()
        msg = await ctx.send(content, view=view)
        view.message = msg

    @commands.command(name="status", aliases=["st"], help="查看隊列狀態")
    async def queue_status(self, ctx: commands.Context):
        async with self.lock:
            if not self.lobby and not self.current_teams:
                await ctx.send("📋 目前沒有活動的隊列或分隊。")
                return

            embed = discord.Embed(title="📋 隊列狀態", color=discord.Color.blue())

            # 隊列信息
            if self.lobby:
                lobby_list = '\n'.join(
                    [f"{i+1}. {name}" for i, name in enumerate(self.lobby.values())])
                max_text = f" / {self.max_players}" if self.max_players else ""
                embed.add_field(
                    name=f"隊列成員 ({len(self.lobby)}{max_text} 人)",
                    value=lobby_list,
                    inline=False
                )

            # 分隊信息
            if self.current_teams:
                team_info = []
                for i, team in enumerate(self.current_teams, 1):
                    team_names = []
                    for uid in team:
                        member = ctx.guild.get_member(uid)
                        if member:
                            team_names.append(member.display_name)
                    team_info.append(f"Team {i}: {', '.join(team_names)}")

                embed.add_field(
                    name=f"已分隊結果 ({len(self.current_teams)} 隊)",
                    value='\n'.join(team_info),
                    inline=False
                )

            await ctx.send(embed=embed)

    async def execute_team_division(self, interaction: discord.Interaction, teams: int, players_per_team: int = None, is_reshuffle: bool = False):
        """執行分隊邏輯"""
        async with self.lock:
            total_players = len(self.lobby)

            # 計算實際分隊參數
            if players_per_team is None:
                if total_players <= 4:
                    calculated_teams = 2
                elif total_players <= 10:
                    calculated_teams = 2 if total_players % 2 == 0 else 3
                else:
                    calculated_teams = min(4, total_players // 3)

                teams = min(teams, calculated_teams)
                players_per_team = total_players // teams

            # 驗證參數
            if teams < 1 or players_per_team < 1:
                await interaction.response.send_message("⚠️ 隊伍數和每隊人數都必須至少為 1", ephemeral=True)
                return

            if teams > total_players:
                await interaction.response.send_message(f"⚠️ 隊伍數 ({teams}) 不能超過總人數 ({total_players})", ephemeral=True)
                return

            # 計算實際分隊人數
            max_players_possible = teams * players_per_team
            selected_ids = list(self.lobby.keys())[:max_players_possible]

            # 執行分隊
            success = await self._perform_team_division(interaction, teams, players_per_team, selected_ids, is_reshuffle)

            if success:
                # 保存分隊設定
                self.team_settings = {
                    'teams': teams,
                    'players_per_team': players_per_team
                }

                # 更新隊列顯示
                if hasattr(interaction, 'message') and interaction.message:
                    view = InviteView(
                        self, self.lobby, message=interaction.message, lock=self.lock,
                        max_players=self.max_players, queue_creator=self.queue_creator
                    )
                    content = await view._generate_queue_content()
                    try:
                        await interaction.message.edit(content=content, view=view)
                    except:
                        pass

    async def _perform_team_division(self, interaction: discord.Interaction, teams: int, players_per_team: int, player_ids: list, is_reshuffle: bool = False):
        """執行分隊和語音頻道操作"""
        # 洗牌分隊
        random.shuffle(player_ids)

        # 創建隊伍
        team_lists = []
        start = 0
        for i in range(teams):
            end = min(start + players_per_team, len(player_ids))
            team = player_ids[start:end]
            if team:
                team_lists.append(team)
            start = end

        # 保存分隊結果
        self.current_teams = team_lists

        # 顯示分隊結果
        embed = discord.Embed(
            title="⚡ 重新分隊結果" if is_reshuffle else "⚡ 分隊結果",
            color=discord.Color.gold()
        )

        for i, team in enumerate(team_lists, 1):
            mentions = []
            for uid in team:
                member = interaction.guild.get_member(uid)
                if member:
                    mentions.append(member.display_name)

            embed.add_field(
                name=f"🔸 Team {i} ({len(team)} 人)",
                value='\n'.join(mentions),
                inline=True
            )

        if not is_reshuffle:
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # 嘗試創建語音頻道（如果有權限）
        guild = interaction.guild
        bot_member = guild.me

        if (bot_member.guild_permissions.manage_channels and
                bot_member.guild_permissions.move_members):
            try:
                await self._create_voice_channels(guild, len(team_lists))
            except Exception as e:
                print(f"創建語音頻道失敗: {e}")

        return True

    async def _create_voice_channels(self, guild: discord.Guild, team_count: int):
        """創建語音頻道"""
        try:
            category = discord.utils.get(guild.categories, name="Voice / 2")
            if not category:
                category = await guild.create_category("Voice / 2")
        except Exception as e:
            print(f"建立分類頻道失敗: {e}")
            return False

        # 清理舊的team頻道
        for channel in guild.voice_channels:
            if channel.name.startswith("team-") and channel.category == category:
                try:
                    await channel.delete()
                except Exception:
                    pass

        # 創建新頻道
        try:
            for i in range(team_count):
                await guild.create_voice_channel(f"team-{i+1}", category=category)
                await asyncio.sleep(0.5)  # 避免API限制
        except Exception as e:
            print(f"創建語音頻道失敗: {e}")
            return False

        return True

    async def move_players_to_voice(self, guild: discord.Guild) -> int:
        """移動玩家到對應的語音頻道"""
        moved_count = 0

        for i, team in enumerate(self.current_teams):
            team_channel = discord.utils.get(
                guild.voice_channels, name=f"team-{i+1}")
            if not team_channel:
                continue

            for uid in team:
                member = guild.get_member(uid)
                if member and member.voice and member.voice.channel:
                    try:
                        await member.move_to(team_channel)
                        moved_count += 1
                        await asyncio.sleep(0.2)
                    except Exception as e:
                        print(f"移動 {member.display_name} 失敗: {e}")

        return moved_count

    async def return_players_to_original(self, guild: discord.Guild) -> int:
        """拉回玩家到原始頻道"""
        if not self.original_voice_channel:
            return 0

        # 檢查原始頻道是否還存在
        original_channel = guild.get_channel(self.original_voice_channel.id)
        if not original_channel:
            return 0

        moved_count = 0

        # 只拉回在team-頻道中的玩家
        for channel in guild.voice_channels:
            if channel.name.startswith("team-"):
                for member in channel.members:
                    try:
                        await member.move_to(original_channel)
                        moved_count += 1
                        await asyncio.sleep(0.2)
                    except Exception as e:
                        print(f"拉回 {member.display_name} 失敗: {e}")

        return moved_count

    @commands.command(name="start", help="開始分隊 - 用法: !start [隊伍數] [每隊人數]")
    async def start_teams(
        self, ctx: commands.Context, teams: int = None, players_per_team: int = None
    ):
        """保留原始的指令式分隊功能"""
        async with self.lock:
            total_players = len(self.lobby)

            if total_players < 2:
                await ctx.send("⚠️ 隊列至少需要 2 人才能開始分隊。")
                return

            # 智能預設值計算
            if teams is None and players_per_team is None:
                if total_players <= 4:
                    teams = 2
                elif total_players <= 10:
                    teams = 2 if total_players % 2 == 0 else 3
                else:
                    teams = min(4, total_players // 3)
                players_per_team = total_players // teams

            elif teams is not None and players_per_team is None:
                if teams > total_players:
                    await ctx.send(f"⚠️ 隊伍數 ({teams}) 不能超過總人數 ({total_players})。")
                    return
                players_per_team = total_players // teams

            elif teams is None and players_per_team is not None:
                if players_per_team > total_players:
                    await ctx.send(f"⚠️ 每隊人數 ({players_per_team}) 不能超過總人數 ({total_players})。")
                    return
                teams = total_players // players_per_team

            # 驗證參數
            if teams < 1 or players_per_team < 1:
                await ctx.send("⚠️ 隊伍數和每隊人數都必須至少為 1。")
                return

            # 計算實際會被分隊的人數
            max_players_possible = teams * players_per_team
            selected_ids = list(self.lobby.keys())[:max_players_possible]

            # 顯示分隊資訊
            remaining = total_players - len(selected_ids)
            if remaining > 0:
                await ctx.send(f"ℹ️ 將分成 {teams} 隊，每隊 {players_per_team} 人。剩餘 {remaining} 人將留在隊列中。")

            # 清空被分隊的玩家
            for uid in selected_ids:
                self.lobby.pop(uid, None)

        # 執行分隊
        success = await self._distribute_and_move(ctx, teams, players_per_team, selected_ids)
        if success:
            await ctx.send("🎉 分隊完成！祝遊戲愉快！")

    async def _distribute_and_move(self, ctx, teams, players_per_team, player_ids):
        """原始的分隊和移動邏輯（保持向後兼容）"""
        # 洗牌分隊
        random.shuffle(player_ids)

        # 切割分隊
        team_lists = []
        start = 0
        for i in range(teams):
            end = min(start + players_per_team, len(player_ids))
            team = player_ids[start:end]
            if team:
                team_lists.append(team)
            start = end

        # 發送分隊結果
        embed = discord.Embed(title="⚡ 分隊結果", color=discord.Color.gold())

        for i, team in enumerate(team_lists, start=1):
            mentions = '\n'.join(f"<@{uid}>" for uid in team)
            embed.add_field(
                name=f"🔸 Team {i} ({len(team)} 人)",
                value=mentions,
                inline=True
            )

        await ctx.send(embed=embed)

        # 創建語音頻道
        guild = ctx.guild
        try:
            category = discord.utils.get(guild.categories, name="Voice / 2")
            if not category:
                category = await guild.create_category("Voice / 2")
        except Exception as e:
            await ctx.send(f"⚠️ 建立分類頻道失敗: {e}")
            return False

        voice_channels = []
        try:
            for i in range(len(team_lists)):
                vc = await guild.create_voice_channel(f"team-{i+1}", category=category)
                voice_channels.append(vc)
                await asyncio.sleep(0.5)
        except Exception as e:
            # 清理已建立的頻道
            for vc in voice_channels:
                try:
                    await vc.delete()
                except Exception:
                    pass
            await ctx.send(f"⚠️ 建立語音頻道失敗: {e}")
            return False

        # 移動玩家到對應頻道
        moved_count = 0
        for i, team in enumerate(team_lists):
            vc = voice_channels[i]
            for uid in team:
                member = guild.get_member(uid)
                if member and member.voice and member.voice.channel:
                    try:
                        await member.move_to(vc)
                        moved_count += 1
                        await asyncio.sleep(0.2)
                    except Exception as e:
                        print(f"無法移動 {member.display_name} 至 {vc.name}: {e}")

        if moved_count > 0:
            await ctx.send(f"✅ 已移動 {moved_count} 名玩家到對應的語音頻道。")

        return True

    @commands.command(name="start-f", help="強制分隊（管理員專用）")
    @commands.has_permissions(administrator=True)
    async def force_start(self, ctx: commands.Context, teams: int = 2):
        async with self.lock:
            total_players = len(self.lobby)
            if teams < 1:
                await ctx.send("⚠️ 隊伍數必須至少 1 隊。")
                return
            if total_players == 0:
                await ctx.send("⚠️ 隊列沒有人，無法分隊。")
                return

            selected_ids = list(self.lobby.keys())

            # 清空隊列
            self.lobby.clear()

        # 平均分配，允許隊伍人數不同
        base_players = total_players // teams
        extra_players = total_players % teams

        # 創建隊伍人數列表
        team_sizes = [base_players +
                      (1 if i < extra_players else 0) for i in range(teams)]

        await ctx.send(f"⚡ 強制分隊：{total_players} 人分成 {teams} 隊")

        success = await self._distribute_and_move_flexible(ctx, team_sizes, selected_ids)
        if success:
            await ctx.send("🎉 強制分隊完成！")

    async def _distribute_and_move_flexible(self, ctx, team_sizes, player_ids):
        """彈性分隊，允許每隊人數不同"""
        random.shuffle(player_ids)

        team_lists = []
        start = 0
        for size in team_sizes:
            team = player_ids[start:start + size]
            team_lists.append(team)
            start += size

        # 顯示分隊結果
        embed = discord.Embed(title="⚡ 強制分隊結果", color=discord.Color.red())

        for i, team in enumerate(team_lists, start=1):
            mentions = '\n'.join(f"<@{uid}>" for uid in team)
            embed.add_field(
                name=f"🔸 Team {i} ({len(team)} 人)",
                value=mentions,
                inline=True
            )

        await ctx.send(embed=embed)

        # 語音頻道創建和移動邏輯
        guild = ctx.guild
        try:
            category = discord.utils.get(guild.categories, name="Voice / 2")
            if not category:
                category = await guild.create_category("Voice / 2")
        except Exception as e:
            await ctx.send(f"⚠️ 建立分類頻道失敗: {e}")
            return False

        voice_channels = []
        try:
            for i in range(len(team_lists)):
                vc = await guild.create_voice_channel(f"team-{i+1}", category=category)
                voice_channels.append(vc)
                await asyncio.sleep(0.5)
        except Exception as e:
            for vc in voice_channels:
                try:
                    await vc.delete()
                except Exception:
                    pass
            await ctx.send(f"⚠️ 建立語音頻道失敗: {e}")
            return False

        # 移動玩家
        moved_count = 0
        for i, team in enumerate(team_lists):
            vc = voice_channels[i]
            for uid in team:
                member = guild.get_member(uid)
                if member and member.voice and member.voice.channel:
                    try:
                        await member.move_to(vc)
                        moved_count += 1
                        await asyncio.sleep(0.2)
                    except Exception as e:
                        print(f"無法移動 {member.display_name} 至 {vc.name}: {e}")

        if moved_count > 0:
            await ctx.send(f"✅ 已移動 {moved_count} 名玩家到對應的語音頻道。")

        return True

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ):
        # 自動清理空的team頻道
        if before.channel and before.channel.name.startswith("team-"):
            if len(before.channel.members) == 0:
                try:
                    await asyncio.sleep(5)  # 等待5秒避免誤刪
                    if len(before.channel.members) == 0:  # 再次確認
                        await before.channel.delete()
                        print(f"自動刪除空語音頻道：{before.channel.name}")
                except Exception as e:
                    print(f"刪除語音頻道失敗: {e}")

    @commands.command(name="game", aliases=["games"], help="查看遊戲清單")
    async def list_games(self, ctx: commands.Context):
        try:
            games = await read_json(GAME_FILE)
            if not games or not isinstance(games, dict) or "urls" not in games:
                await ctx.send("📋 目前沒有遊戲清單。")
                return

            urls = games["urls"]
            if not urls:
                await ctx.send("📋 遊戲清單是空的。")
                return

            embed = discord.Embed(title="🎮 遊戲清單", color=discord.Color.green())

            # 根據JSON結構，urls是一個包含字典的數組
            if isinstance(urls, list):
                for game in urls:
                    if isinstance(game, dict) and "name" in game and "url" in game:
                        embed.add_field(
                            name=game["name"],
                            value=f"[點擊遊玩]({game['url']})",
                            inline=False
                        )
            else:
                await ctx.send("⚠️ 遊戲清單格式不正確。")
                return

            if len(embed.fields) == 0:
                await ctx.send("📋 遊戲清單中沒有有效的遊戲項目。")
                return

            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"⚠️ 讀取遊戲清單時發生錯誤: {e}")


async def setup(bot):
    await bot.add_cog(Party(bot))
