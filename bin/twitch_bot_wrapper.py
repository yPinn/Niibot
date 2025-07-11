"""
Twitch Bot 包裝器
為統一啟動器提供 Twitch Bot 的封裝介面
"""

import asyncio
import os
import sys
import logging
import importlib.util

# 設定日誌
logger = logging.getLogger('TwitchBotWrapper')

class TwitchBotWrapper:
    """Twitch Bot 包裝器"""
    
    def __init__(self):
        self.bot = None
        self.is_running = False
        self._setup_environment()
    
    def _setup_environment(self):
        """設定 Twitch Bot 環境"""
        # 添加 twitch-bot 目錄到 Python 路徑
        twitch_bot_path = os.path.join(os.path.dirname(__file__), 'twitch-bot')
        if twitch_bot_path not in sys.path:
            sys.path.insert(0, twitch_bot_path)
        
        # 切換到 twitch-bot 目錄 (重要：讓相對路徑正確)
        self.original_cwd = os.getcwd()
        os.chdir(twitch_bot_path)
        logger.info(f"📁 切換到 Twitch Bot 目錄: {twitch_bot_path}")
    
    async def start(self):
        """啟動 Twitch Bot"""
        try:
            # 動態導入 Twitch Bot 模組
            logger.info("📦 正在導入 Twitch Bot 模組...")
            
            # 導入配置
            from shared.config.modular_config import config
            
            # 驗證配置
            if not config.get_twitch_config('BOT_TOKEN'):
                raise ValueError("Twitch Bot 配置驗證失敗：缺少 BOT_TOKEN")
            
            # 導入 TwitchIO
            try:
                import twitchio
                from twitchio.ext import commands
            except ImportError:
                logger.error("❌ 找不到 twitchio 套件，請安裝: pip install twitchio")
                raise
            
            # 創建 bot 實例 (TwitchIO 2.x 格式)
            self.bot = commands.Bot(
                token=config.get_twitch_config('BOT_TOKEN'),
                prefix=config.get_twitch_config('COMMAND_PREFIX', '!'),
                initial_channels=config.get_twitch_config('INITIAL_CHANNELS', [])
            )
            
            # 設定事件處理器
            self._setup_event_handlers()
            
            # 載入 cogs
            await self._load_extensions()
            
            # 啟動 bot
            logger.info("🎮 Twitch Bot 準備啟動...")
            self.is_running = True
            
            await self.bot.start()
            
        except Exception as e:
            logger.error(f"❌ Twitch Bot 啟動失敗: {e}")
            self.is_running = False
            raise
    
    def _setup_event_handlers(self):
        """設定事件處理器"""
        @self.bot.event()
        async def event_ready():
            logger.info(f"🎮 Twitch Bot 已連線: {self.bot.nick}")
            logger.info(f"📺 加入頻道: {', '.join([ch.name for ch in self.bot.connected_channels])}")
        
        @self.bot.event()
        async def event_message(message):
            # 忽略機器人自己的訊息
            if message.echo:
                return
            
            # 處理指令
            await self.bot.handle_commands(message)
    
    async def _load_extensions(self):
        """載入 Twitch Bot 擴展"""
        try:
            cogs_dir = "cogs"
            if os.path.exists(cogs_dir):
                cog_files = [f for f in os.listdir(cogs_dir) if f.endswith(".py") and f != "__init__.py"]
                
                loaded_count = 0
                for filename in sorted(cog_files):
                    cog_name = filename[:-3]
                    try:
                        # TwitchIO 使用 add_cog 而不是 load_module
                        spec = importlib.util.spec_from_file_location(cog_name, f"cogs/{filename}")
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        
                        # 假設每個 cog 檔案都有一個 setup 函數
                        if hasattr(module, 'setup'):
                            module.setup(self.bot)
                        
                        loaded_count += 1
                        logger.debug(f"✅ 載入 cog: {cog_name}")
                    except Exception as e:
                        logger.warning(f"⚠️ 載入 cog {cog_name} 失敗: {e}")
                
                logger.info(f"📚 成功載入 {loaded_count} 個 Twitch Bot 模組")
            else:
                logger.warning("⚠️ 找不到 cogs 目錄")
                
        except Exception as e:
            logger.error(f"❌ 載入 Twitch Bot 擴展失敗: {e}")
            # Twitch Bot 即使沒有載入擴展也可以運行基本功能
    
    async def close(self):
        """關閉 Twitch Bot"""
        if self.bot and self.is_running:
            logger.info("🛑 正在關閉 Twitch Bot...")
            await self.bot.close()
            self.is_running = False
            logger.info("✅ Twitch Bot 已關閉")
        
        # 恢復原始工作目錄
        if hasattr(self, 'original_cwd'):
            os.chdir(self.original_cwd)
    
    @property
    def status(self):
        """獲取 Bot 狀態"""
        return {
            'running': self.is_running,
            'bot_nick': self.bot.nick if self.bot else None,
            'channels_count': len(self.bot.connected_channels) if self.bot else 0,
            'channels': [ch.name for ch in self.bot.connected_channels] if self.bot else []
        }