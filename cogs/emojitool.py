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

    def track_emoji_usage(self, guild_id: int, text: str):
        """追蹤表情符號使用次數"""
        try:
            pattern = re.compile(r":([a-zA-Z0-9_]+):")
            matches = pattern.findall(text)
            
            if matches:
                guild_stats = self._pending_stats.setdefault(guild_id, {})
                for name in matches:
                    guild_stats[name] = guild_stats.get(name, 0) + 1
                    
        except Exception as e:
            BotLogger.error("EmojiTool", f"追蹤表情符號使用失敗 (Guild: {guild_id})", e)

    async def handle_on_message(self, message: discord.Message):
        # 忽略機器人訊息
        if message.author.bot:
            return

        if not message.guild:
            return

        # 忽略指令訊息（避免與機器人指令衝突）
        from utils.config_manager import config
        prefixes = config.command_prefix if isinstance(config.command_prefix, list) else [config.command_prefix]
        if any(message.content.startswith(prefix) for prefix in prefixes):
            return

        # 除錯用：可以啟用以追蹤方法調用
        # BotLogger.debug("EmojiTool", f"處理訊息: {message.author.display_name}")

        guild_id = message.guild.id

        try:
            # 關鍵字回覆
            keyword_replies = await self.keyword_reply_manager.get_guild_data(guild_id)
            for keyword, reply in keyword_replies.items():
                if keyword.lower() in message.content.lower():
                    replaced_reply = await self.replace_emojis_in_text(guild_id, reply)
                    await message.channel.send(replaced_reply)
                    BotLogger.user_action(
                        "關鍵字回覆", 
                        message.author.id, 
                        guild_id, 
                        f"關鍵字: {keyword}"
                    )
                    break

            # 記錄 emoji 使用次數
            self.track_emoji_usage(guild_id, message.content)
            
        except Exception as e:
            BotLogger.error("EmojiTool", f"處理訊息失敗 (Guild: {guild_id})", e)

    @commands.Cog.listener()
    async def on_ready(self):
        await self.load_data()
        BotLogger.info("EmojiTool", "EmojiTool 已就緒")

    @commands.command(name="emoji_add", help="新增自訂表情符號對應 - 用法: ?emoji_add 名稱 表情符號")
    @commands.has_permissions(manage_messages=True)
    async def add_emoji(self, ctx: commands.Context, name: str, emoji: str):
        """新增自訂表情符號對應"""
        try:
            guild_id = ctx.guild.id
            emoji_map = await self.emoji_data_manager.get_guild_data(guild_id)
            
            emoji_map[name.lower()] = emoji
            await self.emoji_data_manager.update_guild_data(guild_id, emoji_map)
            
            await ctx.send(f"✅ 已新增表情符號對應：`:{name}:` → {emoji}")
            BotLogger.command_used("emoji_add", ctx.author.id, guild_id, f"{name} -> {emoji}")
            
        except Exception as e:
            await ctx.send(f"❌ 新增失敗：{str(e)}")
            BotLogger.error("EmojiTool", "新增表情符號失敗", e)

    @commands.command(name="emoji_list", help="列出所有自訂表情符號")
    async def list_emoji(self, ctx: commands.Context):
        """列出所有自訂表情符號"""
        try:
            guild_id = ctx.guild.id
            emoji_map = await self.emoji_data_manager.get_guild_data(guild_id)
            
            if not emoji_map:
                await ctx.send("📝 目前沒有自訂表情符號對應")
                return
            
            embed = discord.Embed(title="🎭 自訂表情符號列表", color=discord.Color.blue())
            
            for name, emoji in list(emoji_map.items())[:25]:  # 限制顯示數量
                embed.add_field(name=f":{name}:", value=emoji, inline=True)
            
            if len(emoji_map) > 25:
                embed.set_footer(text=f"顯示前 25 個，總共 {len(emoji_map)} 個")
            
            await ctx.send(embed=embed)
            BotLogger.command_used("emoji_list", ctx.author.id, guild_id, f"顯示 {len(emoji_map)} 個表情符號")
            
        except Exception as e:
            await ctx.send(f"❌ 列表取得失敗：{str(e)}")
            BotLogger.error("EmojiTool", "列出表情符號失敗", e)

    @commands.command(name="keyword_add", help="新增關鍵字自動回覆 - 用法: ?keyword_add 關鍵字 回覆內容")
    @commands.has_permissions(manage_messages=True)
    async def add_keyword_reply(self, ctx: commands.Context, keyword: str, *, reply: str):
        """新增關鍵字自動回覆"""
        try:
            guild_id = ctx.guild.id
            keyword_replies = await self.keyword_reply_manager.get_guild_data(guild_id)
            
            keyword_replies[keyword.lower()] = reply
            await self.keyword_reply_manager.update_guild_data(guild_id, keyword_replies)
            
            await ctx.send(f"✅ 已新增關鍵字回覆：`{keyword}` → {reply}")
            BotLogger.command_used("keyword_add", ctx.author.id, guild_id, f"{keyword} -> {reply[:50]}")
            
        except Exception as e:
            await ctx.send(f"❌ 新增失敗：{str(e)}")
            BotLogger.error("EmojiTool", "新增關鍵字回覆失敗", e)

    @commands.command(name="emoji_help", help="顯示表情符號工具的使用說明")
    async def emoji_help(self, ctx: commands.Context):
        """顯示表情符號工具的詳細使用說明"""
        embed = discord.Embed(
            title="🎭 表情符號工具使用說明",
            description="自訂表情符號對應和關鍵字自動回覆功能",
            color=discord.Color.gold()
        )
        
        # 一般使用者功能
        embed.add_field(
            name="📝 查看功能",
            value="• `?emoji_list` - 查看所有自訂表情符號\n• `?emoji_help` - 顯示此說明",
            inline=False
        )
        
        # 管理員功能
        embed.add_field(
            name="⚙️ 管理功能 (需要管理訊息權限)",
            value="• `?emoji_add 名稱 表情符號` - 新增表情符號對應\n• `?keyword_add 關鍵字 回覆內容` - 新增關鍵字回覆",
            inline=False
        )
        
        # 使用範例
        embed.add_field(
            name="💡 使用範例",
            value="```\n?emoji_add happy 😄\n輸入 :happy: 會顯示為 😄\n\n?keyword_add 你好 歡迎！:happy:\n有人說「你好」時自動回覆```",
            inline=False
        )
        
        embed.set_footer(text="表情符號會在關鍵字回覆中自動替換")
        await ctx.send(embed=embed)


async def setup(bot):
    emoji_tool = EmojiTool(bot)
    await emoji_tool.load_data()
    await bot.add_cog(emoji_tool)
    BotLogger.system_event("Cog載入", "EmojiTool cog 已成功載入")
