"""
Discord Bot 包裝器
為統一啟動器提供 Discord Bot 的封裝介面
"""

import asyncio
import os
import sys
import logging

# 設定日誌
logger = logging.getLogger('DiscordBotWrapper')

class DiscordBotWrapper:
    """Discord Bot 包裝器"""
    
    def __init__(self):
        self.bot = None
        self.is_running = False
        self._setup_environment()
    
    def _setup_environment(self):
        """設定 Discord Bot 環境"""
        # 添加 discord-bot 目錄到 Python 路徑
        discord_bot_path = os.path.join(os.path.dirname(__file__), 'discord-bot')
        if discord_bot_path not in sys.path:
            sys.path.insert(0, discord_bot_path)
        
        # 切換到 discord-bot 目錄 (重要：讓相對路徑正確)
        self.original_cwd = os.getcwd()
        os.chdir(discord_bot_path)
        logger.info(f"📁 切換到 Discord Bot 目錄: {discord_bot_path}")
    
    async def start(self):
        """啟動 Discord Bot"""
        try:
            # 動態導入 Discord Bot 模組
            logger.info("📦 正在導入 Discord Bot 模組...")
            
            # 導入必要的模組
            from shared.config.modular_config import config
            import discord
            from discord.ext import commands
            
            # 創建 bot 實例 (模擬原始 bot.py 的邏輯)
            intents = discord.Intents.all()
            self.bot = commands.Bot(command_prefix=config.get_discord_config('COMMAND_PREFIX', '?'), intents=intents)
            
            # 載入 cogs
            await self._load_extensions()
            
            # 啟動 bot
            logger.info("🤖 Discord Bot 準備啟動...")
            self.is_running = True
            
            await self.bot.start(config.get_discord_config('TOKEN'))
            
        except Exception as e:
            logger.error(f"❌ Discord Bot 啟動失敗: {e}")
            self.is_running = False
            raise
    
    async def _load_extensions(self):
        """載入 Discord Bot 擴展"""
        try:
            cogs_dir = "cogs"
            cog_files = [f for f in os.listdir(cogs_dir) if f.endswith(".py")]
            
            loaded_count = 0
            for filename in sorted(cog_files):
                cog_name = filename[:-3]
                try:
                    await self.bot.load_extension(f"cogs.{cog_name}")
                    loaded_count += 1
                    logger.debug(f"✅ 載入 cog: {cog_name}")
                except Exception as e:
                    logger.warning(f"⚠️ 載入 cog {cog_name} 失敗: {e}")
            
            logger.info(f"📚 成功載入 {loaded_count} 個 Discord Bot 模組")
            
        except Exception as e:
            logger.error(f"❌ 載入 Discord Bot 擴展失敗: {e}")
            raise
    
    async def close(self):
        """關閉 Discord Bot"""
        if self.bot and self.is_running:
            logger.info("🛑 正在關閉 Discord Bot...")
            await self.bot.close()
            self.is_running = False
            logger.info("✅ Discord Bot 已關閉")
        
        # 恢復原始工作目錄
        if hasattr(self, 'original_cwd'):
            os.chdir(self.original_cwd)
    
    @property
    def status(self):
        """獲取 Bot 狀態"""
        return {
            'running': self.is_running,
            'bot_user': str(self.bot.user) if self.bot and self.bot.user else None,
            'guilds_count': len(self.bot.guilds) if self.bot else 0
        }