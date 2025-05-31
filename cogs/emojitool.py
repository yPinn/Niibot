import json
import os
import re

import aiofiles
import discord
from discord.ext import commands

from utils.util import format_error_msg, format_success_msg, read_json, write_json

EMOJI_JSON_PATH = "data/emoji.json"
KEYWORD_REPLY_JSON_PATH = "data/keyword_replies.json"
EMOJI_STATS_JSON_PATH = "data/emoji_stats.json"


class EmojiTool(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.emoji_data = {}
        self.keyword_reply_map = {}
        self.emoji_usage_stats = {}

    async def load_data(self):
        await self._load_emojis()
        await self._load_keyword_replies()
        await self._load_emoji_stats()

    async def _load_emojis(self):
        if not os.path.exists(EMOJI_JSON_PATH):
            os.makedirs(os.path.dirname(EMOJI_JSON_PATH), exist_ok=True)
            await write_json(EMOJI_JSON_PATH, {"guild_emojis": {}})
        data = await read_json(EMOJI_JSON_PATH)
        self.emoji_data = data.get("guild_emojis", {})

    async def _load_keyword_replies(self):
        if not os.path.exists(KEYWORD_REPLY_JSON_PATH):
            await write_json(KEYWORD_REPLY_JSON_PATH, {})
        self.keyword_reply_map = await read_json(KEYWORD_REPLY_JSON_PATH)

    async def _load_emoji_stats(self):
        if not os.path.exists(EMOJI_STATS_JSON_PATH):
            await write_json(EMOJI_STATS_JSON_PATH, {})
        self.emoji_usage_stats = await read_json(EMOJI_STATS_JSON_PATH)

    async def save_emoji_stats(self):
        await write_json(EMOJI_STATS_JSON_PATH, self.emoji_usage_stats)

    async def export_emojis(self):
        result = {}
        for guild in self.bot.guilds:
            emoji_map = {emoji.name: str(emoji) for emoji in guild.emojis}
            result[str(guild.id)] = emoji_map
        try:
            await write_json(EMOJI_JSON_PATH, {"guild_emojis": result})
            # 強制重新載入 Emoji 資料
            await self._load_emojis()
            return True, None
        except Exception as e:
            return False, str(e)

    def replace_emojis_in_text(self, guild_id: int, text: str) -> str:
        emoji_map = self.emoji_data.get(str(guild_id), {})
        pattern = re.compile(r":([a-zA-Z0-9_]+):")

        def replacer(match):
            name = match.group(1)
            return emoji_map.get(name, match.group(0))

        return pattern.sub(replacer, text)

    def track_emoji_usage(self, guild_id: int, text: str):
        pattern = re.compile(r":([a-zA-Z0-9_]+):")
        matches = pattern.findall(text)
        stats = self.emoji_usage_stats.setdefault(str(guild_id), {})
        for name in matches:
            stats[name] = stats.get(name, 0) + 1

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        guild_id = str(message.guild.id)

        # 自動回覆邏輯（關鍵字觸發）
        for keyword, reply in self.keyword_reply_map.items():
            if keyword in message.content:
                replaced = self.replace_emojis_in_text(message.guild.id, reply)
                await message.channel.send(replaced)
                break

        # 統計 emoji 使用次數
        self.track_emoji_usage(message.guild.id, message.content)
        await self.save_emoji_stats()

    @commands.command(name="export_emojis")
    @commands.has_permissions(administrator=True)
    async def export_emojis_command(self, ctx):
        success, err = await self.export_emojis()
        if success:
            await ctx.send(format_success_msg("已成功匯出 emoji 資訊到 JSON 並重新載入。"))
        else:
            await ctx.send(format_error_msg(f"匯出失敗：{err}"))

    @commands.command(name="emoji_stats")
    async def emoji_stats_command(self, ctx):
        guild_id = str(ctx.guild.id)
        guild_stats = self.emoji_usage_stats.get(guild_id, {})

        if not guild_stats:
            await ctx.send(format_error_msg("尚無任何 emoji 使用紀錄。"))
            return

        sorted_stats = sorted(guild_stats.items(),
                              key=lambda x: x[1], reverse=True)

        lines = []
        for name, count in sorted_stats[:10]:
            emoji = discord.utils.get(ctx.guild.emojis, name=name)
            if emoji:
                emoji_display = str(emoji)  # 顯示真正貼圖
            else:
                emoji_display = f":{name}:"  # fallback 用文字顯示
            lines.append(f"{emoji_display} - {count} 次")

        await ctx.send("\n".join(lines))

    @commands.command(name="rename_emoji")
    @commands.has_permissions(manage_emojis=True)
    async def rename_emoji(self, ctx, old_name: str, new_name: str):
        emoji = discord.utils.get(ctx.guild.emojis, name=old_name)
        if emoji:
            try:
                await emoji.edit(name=new_name)
                await ctx.send(format_success_msg(f"{old_name} 已重新命名為 {new_name}"))
            except discord.Forbidden:
                await ctx.send(format_error_msg("缺少修改 emoji 權限。"))
            except Exception as e:
                await ctx.send(format_error_msg(f"修改失敗：{e}"))
        else:
            await ctx.send(format_error_msg(f"找不到 emoji: {old_name}"))

    @commands.command(name="delete_emoji")
    @commands.has_permissions(manage_emojis=True)
    async def delete_emoji(self, ctx, name: str):
        emoji = discord.utils.get(ctx.guild.emojis, name=name)
        if emoji:
            try:
                await emoji.delete()
                await ctx.send(format_success_msg(f"已刪除 emoji: {name}"))
            except discord.Forbidden:
                await ctx.send(format_error_msg("缺少刪除 emoji 權限。"))
            except Exception as e:
                await ctx.send(format_error_msg(f"刪除失敗：{e}"))
        else:
            await ctx.send(format_error_msg(f"找不到 emoji: {name}"))


async def setup(bot):
    emoji_tool = EmojiTool(bot)
    await emoji_tool.load_data()
    await bot.add_cog(emoji_tool)
    bot.emoji_tool = emoji_tool
