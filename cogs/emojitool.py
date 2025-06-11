import os
import re
import asyncio
import discord
from discord.ext import commands
from utils import util
from utils.logger import BotLogger
from utils.config_manager import config
from utils.util import GuildDataManager


class EmojiTool(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.emoji_data_manager = GuildDataManager("emoji.json", {})
        self.keyword_reply_manager = GuildDataManager("keyword_replies.json", {})
        self.emoji_stats_manager = GuildDataManager("emoji_stats.json", {})
        self._save_task = None
        self._pending_stats = {}
        BotLogger.info("EmojiTool", "EmojiTool cog 初始化完成")

    async def load_data(self):
        try:
            await self.emoji_data_manager.load_data()
            await self.keyword_reply_manager.load_data()
            await self.emoji_stats_manager.load_data()
            BotLogger.info("EmojiTool", "資料載入完成")
            # 延遲啟動定期儲存，避免載入時阻塞
            asyncio.create_task(self._delayed_start_periodic_save())
        except Exception as e:
            BotLogger.error("EmojiTool", "載入資料失敗", e)

    async def _delayed_start_periodic_save(self):
        """延遲啟動定期儲存，避免載入時阻塞"""
        await asyncio.sleep(2)  # 等待 2 秒確保其他載入完成
        self._start_periodic_save()
    
    def _start_periodic_save(self):
        """啟動定期儲存任務"""
        if self._save_task is None or self._save_task.done():
            self._save_task = asyncio.create_task(self._periodic_save())
    
    async def _periodic_save(self):
        """定期儲存表情符號統計"""
        while True:
            try:
                await asyncio.sleep(config.emoji_save_interval)
                if self._pending_stats:
                    await self._flush_pending_stats()
            except Exception as e:
                BotLogger.error("EmojiTool", "定期儲存失敗", e)
    
    async def _flush_pending_stats(self):
        """清空待處理的統計資料"""
        if not self._pending_stats:
            return
            
        try:
            for guild_id, stats in self._pending_stats.items():
                current_stats = await self.emoji_stats_manager.get_guild_data(guild_id)
                for emoji_name, count in stats.items():
                    current_stats[emoji_name] = current_stats.get(emoji_name, 0) + count
                await self.emoji_stats_manager.update_guild_data(guild_id, current_stats)
            
            saved_count = sum(len(stats) for stats in self._pending_stats.values())
            self._pending_stats.clear()
            BotLogger.debug("EmojiTool", f"已儲存 {saved_count} 個表情符號統計")
        except Exception as e:
            BotLogger.error("EmojiTool", "清空待處理統計失敗", e)

    async def replace_emojis_in_text(self, guild_id: int, text: str) -> str:
        try:
            emoji_map = await self.emoji_data_manager.get_guild_data(guild_id)
            pattern = re.compile(r":([a-zA-Z0-9_]+):")

            def replacer(match):
                name = match.group(1)
                return emoji_map.get(name, match.group(0))
                
            return pattern.sub(replacer, text)
        except Exception as e:
            BotLogger.error("EmojiTool", f"替換表情符號失敗 (Guild: {guild_id})", e)
            return text

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
