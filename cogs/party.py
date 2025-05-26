import asyncio
import os
import random

import discord
from discord.ext import commands
from discord.ui import View

from utils.util import read_json  # 你的同步讀json函式，建議改非同步版本 await read_json_async()

DATA_DIR = "data"
GAME_FILE = os.path.join(DATA_DIR, "game.json")


class InviteView(View):
    def __init__(self, queue: dict, message: discord.Message = None, lock: asyncio.Lock = None):
        super().__init__(timeout=None)
        self.queue = queue  # dict: {user_id: display_name}
        self.message = message
        self.lock = lock  # 用來保護 queue 同步操作

    @discord.ui.button(label="Queue",
                       style=discord.ButtonStyle.success,
                       custom_id="toggle_queue")
    async def toggle_queue(self, interaction: discord.Interaction,
                           button: discord.ui.Button):
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
                        content=f"[目前有 {len(self.queue)} / 10 人]\n{lobby}", view=self)
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
                    content=f"[目前有 {len(self.queue)} / 10 人]\n{lobby}", view=self)

        await interaction.response.send_message(msg_text, ephemeral=True)


class Party(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queue = {}  # dict user_id -> display_name
        self.lock = asyncio.Lock()

    @commands.command(name="queue", help="分隊大廳")
    async def queue(self, ctx: commands.Context):
        """顯示配對大廳與加入/離開排隊按鈕"""
        view = InviteView(self.queue, lock=self.lock)
        msg = await ctx.send("配對大廳：", view=view)
        view.message = msg

    @commands.command(name="mf", help="分隊(語音)")
    async def teamup(self, ctx: commands.Context):
        """將排隊玩家隨機分兩隊並建立語音頻道"""
        async with self.lock:
            ids = list(self.queue.keys())
            if len(ids) < 2:
                await ctx.send("⚠️ 隊列中人數不足，無法分隊。")
                return

            random.shuffle(ids)
            mid = len(ids) // 2
            team1 = ids[:mid]
            team2 = ids[mid:]

            # 清空隊列
            self.queue.clear()

        def format_team(team):
            return '\n'.join([f"<@{uid}>" for uid in team])

        await ctx.send(
            f"**Team 1**:\n{format_team(team1)}\n\n**Team 2**:\n{format_team(team2)}"
        )

        try:
            guild = ctx.guild
            category = discord.utils.get(guild.categories, name="Voice / 2")
            if not category:
                category = await guild.create_category("Voice / 2")
        except Exception as e:
            await ctx.send(f"⚠️ 建立分類頻道失敗: {e}")
            return

        # 建立語音頻道
        vc1 = await guild.create_voice_channel("team-1", category=category)
        vc2 = await guild.create_voice_channel("team-2", category=category)

        for uid in team1:
            member = guild.get_member(uid)
            if member and member.voice:
                try:
                    await member.move_to(vc1)
                except Exception as e:
                    print(f"無法移動 {member.display_name}: {e}")

        for uid in team2:
            member = guild.get_member(uid)
            if member and member.voice:
                try:
                    await member.move_to(vc2)
                except Exception as e:
                    print(f"無法移動 {member.display_name}: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):

        # 如果離開了一個語音頻道，且該語音頻道以 team- 開頭且無人，則刪除它
        if before.channel and before.channel.name.startswith("team-"):
            if len(before.channel.members) == 0:
                try:
                    await before.channel.delete()
                except Exception as e:
                    print(f"刪除語音頻道失敗: {e}")

    @commands.command(name="game")
    async def list_games(self, ctx: commands.Context):
        games = await read_json(GAME_FILE)
        print("讀取的 games:", games)  # 加印 debug

        if not games or not isinstance(games, dict) or "urls" not in games:
            await ctx.send("⚠️ 找不到遊戲資料或資料格式錯誤。")
            return

        url_list = games.get("urls", [])
        if not url_list:
            await ctx.send("⚠️ 遊戲網址清單為空。")
            return

        lines = [
            f"**{entry['name']}**: {entry['url']}" for entry in url_list if 'name' in entry and 'url' in entry]
        msg = "\n".join(lines)

        await ctx.send(f"🎮 目前遊戲列表：\n{msg}")

    @commands.command(name="codenames")
    async def list_codenames_themes(self, ctx: commands.Context, *, topic_name: str = None):
        """列出 Codenames 的主題，或顯示特定主題的所有詞語"""
        games = await read_json(GAME_FILE)
        codenames = games.get("CodeNames", {})
        themes = codenames.get("themes", [])

        if not themes:
            await ctx.send("⚠️ 找不到 Codenames 主題資料。")
            return

        if topic_name:
            # 查詢特定主題
            for theme in themes:
                if theme.get("topic") == topic_name:
                    words = theme.get("words", [])
                    if not words:
                        await ctx.send(f"⚠️ 主題 **{topic_name}** 沒有任何詞語。")
                        return
                    word_list = "\n".join(words)
                    await ctx.send(f"🧠 **{topic_name}** 主題共有 {len(words)} 個詞：\n{word_list}")

                    return
            await ctx.send(f"⚠️ 找不到主題 **{topic_name}**，請確認名稱是否正確。")
        else:
            # 顯示所有主題與數量
            lines = [
                f"🔹 **{theme.get('topic', '未命名主題')}**（{len(theme.get('words', []))} 個詞）" for theme in themes]
            await ctx.send(f"🧠 Codenames 主題列表：\n" + "\n".join(lines))


async def setup(bot: commands.Bot):
    await bot.add_cog(Party(bot))
