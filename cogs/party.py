import asyncio
import os
import random

import discord
from discord.ext import commands
from discord.ui import View

from utils.util import read_json  # 假設是非同步版本

DATA_DIR = "data"
GAME_FILE = os.path.join(DATA_DIR, "game.json")


class InviteView(View):
    def __init__(self, queue: dict, message: discord.Message = None, lock: asyncio.Lock = None):
        super().__init__(timeout=None)
        self.queue = queue  # dict: {user_id: display_name}
        self.message = message
        self.lock = lock  # 用來保護 queue 同步操作

    @discord.ui.button(label="Queue", style=discord.ButtonStyle.success, custom_id="toggle_queue")
    async def toggle_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        display_name = interaction.user.display_name

        if self.lock:
            async with self.lock:
                if user_id in self.queue:
                    self.queue.pop(user_id)
                    msg_text = f"{interaction.user.mention} 已離開列隊。"
                else:
                    if len(self.queue) >= 10:
                        await interaction.response.send_message("⚠️ 隊列已滿", ephemeral=True)
                        return
                    self.queue[user_id] = display_name
                    msg_text = f"{interaction.user.mention} 已加入列隊。"
                lobby = '\n'.join(self.queue.values())
                if self.message:
                    await self.message.edit(
                        content=f"[目前有 {len(self.queue)} / 10 人]\n{lobby}", view=self
                    )
        else:
            # 若沒提供鎖，直接操作（不推薦）
            if user_id in self.queue:
                self.queue.pop(user_id)
                msg_text = f"{interaction.user.mention} 已離開列隊。"
            else:
                if len(self.queue) >= 10:
                    await interaction.response.send_message("⚠️ 隊列已滿", ephemeral=True)
                    return
                self.queue[user_id] = display_name
                msg_text = f"{interaction.user.mention} 已加入列隊。"
            lobby = '\n'.join(self.queue.values())
            if self.message:
                await self.message.edit(
                    content=f"[目前有 {len(self.queue)} / 10 人]\n{lobby}", view=self
                )

        await interaction.response.send_message(msg_text, ephemeral=True)


class Party(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queue = {}  # dict user_id -> display_name
        self.lock = asyncio.Lock()
        self.cleanup_task = self.bot.loop.create_task(
            self.cleanup_empty_voice_channels())

    def cog_unload(self):
        self.cleanup_task.cancel()  # Cog 卸載時取消任務

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
            await asyncio.sleep(60)  # 每 60 秒檢查一次

    @commands.command(name="queue", aliases=["q"], help="分隊大廳")
    async def queue(self, ctx: commands.Context):
        """顯示配對大廳與加入/離開排隊按鈕"""
        view = InviteView(self.queue, lock=self.lock)
        msg = await ctx.send("配對大廳：", view=view)
        view.message = msg

    async def _distribute_and_move(self, ctx, teams, players_per_team, player_ids):
        # 洗牌
        random.shuffle(player_ids)

        # 切割分隊
        team_lists = []
        start = 0
        for i in range(teams):
            team = player_ids[start: start + players_per_team]
            team_lists.append(team)
            start += players_per_team

        # 發送分隊訊息
        msg_lines = []
        for i, team in enumerate(team_lists, start=1):
            mentions = '\n'.join(f"<@{uid}>" for uid in team)
            msg_lines.append(f"**Team {i}** ({len(team)} 人):\n{mentions}")

        await ctx.send("⚡ **分隊結果：**\n" + "\n\n".join(msg_lines))

        guild = ctx.guild
        try:
            category = discord.utils.get(guild.categories, name="Voice / 2")
            if not category:
                category = await guild.create_category("Voice / 2")
        except Exception as e:
            await ctx.send(f"⚠️ 建立分類頻道失敗: {e}")
            return False

        voice_channels = []
        for i in range(teams):
            try:
                vc = await guild.create_voice_channel(f"team-{i+1}", category=category)
                voice_channels.append(vc)
            except Exception as e:
                await ctx.send(f"⚠️ 建立語音頻道 team-{i+1} 失敗: {e}")
                return False

        for i, team in enumerate(team_lists):
            vc = voice_channels[i]
            for uid in team:
                member = guild.get_member(uid)
                if member and member.voice and member.voice.channel:
                    try:
                        await member.move_to(vc)
                    except Exception as e:
                        print(f"無法移動 {member.display_name} 至 {vc.name}: {e}")

        return True

    @commands.command(name="start", help="開始分隊，用法: !start [隊伍數] [每隊人數]")
    async def start_teams(self, ctx: commands.Context, teams: int = None, players_per_team: int = None):
        async with self.lock:
            total_players = len(self.queue)

            # 預設值（沒輸入時）
            if teams is None and players_per_team is None:
                teams = 2
                players_per_team = total_players // teams if total_players >= 2 else 1

            elif teams is not None and players_per_team is None:
                # 只輸入隊伍數
                players_per_team = total_players // teams if total_players >= teams else 1

            elif teams is None and players_per_team is not None:
                # 只輸入每隊人數，算隊伍數
                teams = (total_players + players_per_team -
                         1) // players_per_team  # 向上取整

            # 檢查合理性
            if teams < 1:
                await ctx.send("⚠️ 隊伍數必須至少 1 隊。")
                return
            if players_per_team < 1:
                await ctx.send("⚠️ 每隊人數必須至少 1 人。")
                return

            max_players_possible = teams * players_per_team
            if max_players_possible > total_players:
                await ctx.send(f"⚠️ 目前隊列中有 {total_players} 人，無法分成 {teams} 隊，每隊 {players_per_team} 人。")
                return

            # 依照隊伍數和每隊人數，來決定分隊
            selected_ids = list(self.queue.keys())[:max_players_possible]

            # 清空已加入隊列的玩家（只清空被分隊的人）
            for uid in selected_ids:
                self.queue.pop(uid, None)

        await self._distribute_and_move(ctx, teams, players_per_team, selected_ids)

    @commands.command(name="start-f", help="強制開始分隊（管理員專用）")
    @commands.has_permissions(administrator=True)
    async def force_start(self, ctx: commands.Context, teams: int = 2):
        async with self.lock:
            total_players = len(self.queue)
            if teams < 1:
                await ctx.send("⚠️ 隊伍數必須至少 1 隊。")
                return
            if total_players == 0:
                await ctx.send("⚠️ 隊列沒有人，無法分隊。")
                return

            # 不限制隊伍數要小於人數，強制開始
            selected_ids = list(self.queue.keys())

            # 清空已加入隊列的玩家
            for uid in selected_ids:
                self.queue.pop(uid, None)

        # 計算平均每隊人數（平均分配）
        players_per_team = (total_players + teams - 1) // teams  # 向上取整

        await self._distribute_and_move(ctx, teams, players_per_team, selected_ids)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ):
        if before.channel and before.channel.name.startswith("team-"):
            if len(before.channel.members) == 0:
                try:
                    await before.channel.delete()
                except Exception as e:
                    print(f"刪除語音頻道失敗: {e}")

    @commands.command(name="game")
    async def list_games(self, ctx: commands.Context):
        games = await read_json(GAME_FILE)
        if not games or not isinstance(games, dict) or "urls" not in games:
            await ctx.send("目前沒有遊戲清單。")
            return
        urls = games["urls"]
        msg = "\n".join(f"{name}: {url}" for name, url in urls.items())
        await ctx.send(f"目前遊戲清單：\n{msg}")


async def setup(bot):
    await bot.add_cog(Party(bot))
