import os
import re
import aiofiles
import json

import discord
from discord.ext import commands
from utils.util import read_json, write_json, format_error_msg, format_success_msg
import asyncio

EMOJI_JSON_PATH = "data/emoji.json"


class EmojiTool(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.emoji_data = {}
        self._cooldown_users = set()

    async def load_emojis(self):
        if not os.path.exists(EMOJI_JSON_PATH):
            os.makedirs(os.path.dirname(EMOJI_JSON_PATH), exist_ok=True)
            async with aiofiles.open(EMOJI_JSON_PATH, 'w', encoding='utf-8') as f:
                await f.write('{"guild_emojis": {}}')
            print(f"✅ 建立空的 emoji 資料檔：{EMOJI_JSON_PATH}")

        try:
            async with aiofiles.open(EMOJI_JSON_PATH, 'r', encoding='utf-8') as f:
                content = await f.read()
                self.emoji_data = json.loads(content).get("guild_emojis", {})
            print("✅ Emoji 資料載入完成")
        except Exception as e:
            print(f"❌ 載入失敗：{e}")

    async def export_emojis(self):
        result = {}
        for guild in self.bot.guilds:
            emoji_map = {emoji.name: str(emoji) for emoji in guild.emojis}
            result[str(guild.id)] = emoji_map
        try:
            await write_json(EMOJI_JSON_PATH, {"guild_emojis": result})
            print(format_success_msg("Emoji 資訊已匯出至 JSON"))
            self.emoji_data = result
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

    @commands.command(name="export_emojis")
    @commands.has_permissions(administrator=True)
    async def export_emojis_command(self, ctx):
        success, err = await self.export_emojis()
        if success:
            await ctx.send(format_success_msg("已成功匯出 emoji 資訊到 JSON 檔案。"))
        else:
            await ctx.send(format_error_msg(f"匯出失敗：{err}"))

    async def _cooldown_timer(self, user_id):
        await asyncio.sleep(1)
        self._cooldown_users.discard(user_id)


async def setup(bot):
    emoji_tool = EmojiTool(bot)
    await emoji_tool.load_emojis()
    await bot.add_cog(emoji_tool)
    bot.emoji_tool = emoji_tool
