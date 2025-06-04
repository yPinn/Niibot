import os
import re
import discord
from discord.ext import commands
from utils import util


class EmojiTool(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.emoji_data = {}
        self.keyword_reply_map = {}
        self.emoji_usage_stats = {}
        self.emoji_json_path = "data/emoji.json"
        self.keyword_reply_json_path = "data/keyword_replies.json"
        self.emoji_stats_json_path = "data/emoji_stats.json"

    async def load_data(self):
        await self._load_emojis()
        await self._load_keyword_replies()
        await self._load_emoji_stats()

    async def _load_emojis(self):
        if not os.path.exists(self.emoji_json_path):
            os.makedirs(os.path.dirname(self.emoji_json_path), exist_ok=True)
            await util.write_json(self.emoji_json_path, {"guild_emojis": {}})
        data = await util.read_json(self.emoji_json_path)
        self.emoji_data = data.get("guild_emojis", {})

    async def _load_keyword_replies(self):
        if not os.path.exists(self.keyword_reply_json_path):
            await util.write_json(self.keyword_reply_json_path, {})
        self.keyword_reply_map = await util.read_json(self.keyword_reply_json_path)

    async def _load_emoji_stats(self):
        if not os.path.exists(self.emoji_stats_json_path):
            await util.write_json(self.emoji_stats_json_path, {})
        self.emoji_usage_stats = await util.read_json(self.emoji_stats_json_path)

    async def save_emoji_stats(self):
        await util.write_json(self.emoji_stats_json_path, self.emoji_usage_stats)

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

    async def handle_on_message(self, message: discord.Message):
        # 忽略機器人訊息
        if message.author.bot:
            return

        guild_id = str(message.guild.id)

        # 關鍵字回覆
        for keyword, reply in self.keyword_reply_map.items():
            if keyword in message.content:
                replaced = self.replace_emojis_in_text(message.guild.id, reply)
                await message.channel.send(replaced)
                break

        # 記錄 emoji 使用次數
        self.track_emoji_usage(message.guild.id, message.content)
        await self.save_emoji_stats()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.load_data()
        # 這裡可以做預先匯出或其他啟動工作
        print("[EmojiTool] 已載入資料。")


async def setup(bot):
    emoji_tool = EmojiTool(bot)
    await emoji_tool.load_data()
    await bot.add_cog(emoji_tool)
    bot.emoji_tool = emoji_tool
