import asyncio
import random

import discord
from discord.ext import commands
from discord.ui import View


class InviteView(View):

    def __init__(self, queue: dict, message: discord.Message = None):
        super().__init__(timeout=None)
        self.queue = queue  # dict: {user_id: display_name}
        self.message = message

    @discord.ui.button(label="Queue",
                       style=discord.ButtonStyle.success,
                       custom_id="toggle_queue")
    async def toggle_queue(self, interaction: discord.Interaction,
                           button: discord.ui.Button):
        user_id = interaction.user.id
        display_name = interaction.user.display_name

        if user_id in self.queue:
            self.queue.pop(user_id)
            msg_text = f"{interaction.user.mention} 已離開列隊。"
        else:
            if len(self.queue) >= 10:
                await interaction.response.send_message("⚠️ 隊列已滿",
                                                        ephemeral=True)
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
        self.queue = {}  # 使用 dict: user_id -> display_name

    @commands.command(name="q")
    async def queue(self, ctx: commands.Context):
        view = InviteView(self.queue)
        msg = await ctx.send("配對大廳：", view=view)
        view.message = msg

    @commands.command(name="tu")
    async def teamup(self, ctx: commands.Context):
        ids = list(self.queue.keys())
        if len(ids) < 2:
            await ctx.send("⚠️ 隊列中人數不足，無法分隊。")
            return

        random.shuffle(ids)
        mid = len(ids) // 2
        team1 = ids[:mid]
        team2 = ids[mid:]

        def format_team(team):
            return '\n'.join([f"<@{uid}>" for uid in team])

        await ctx.send(
            f"**Team 1**:\n{format_team(team1)}\n\n**Team 2**:\n{format_team(team2)}"
        )

        guild = ctx.guild
        category = discord.utils.get(guild.categories,
                                     name="Voice / 2")  # 可預先建立一個類別
        if not category:
            category = await guild.create_category("Voice / 2")

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

        # 清空隊列
        self.queue.clear()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # 如果離開了一個語音頻道
        if before.channel and before.channel.name.startswith("team-"):
            if len(before.channel.members) == 0:
                try:
                    await before.channel.delete()
                except Exception as e:
                    print(f"刪除語音頻道失敗: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Party(bot))
