#!/usr/bin/env python3
"""
Niibot 統一啟動器
同時管理 Discord Bot 和 Twitch Bot 的運行
"""

import asyncio
import signal
import sys
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any
import logging
from launcher_utils import SystemMonitor, HealthChecker, GracefulShutdown, create_status_display, periodic_status_display

# 設定基本日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('NiibotLauncher')

class BotManager:
    """Bot 管理器"""
    
    def __init__(self):
        self.discord_bot = None
        self.twitch_bot = None
        self.discord_task = None
        self.twitch_task = None
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.shutdown_event = asyncio.Event()
        self.bots_status = {
            'discord': {'running': False, 'error': None},
            'twitch': {'running': False, 'error': None}
        }
        
        # 新增系統監控和健康檢查
        self.system_monitor = SystemMonitor()
        self.health_checker = HealthChecker(self)
        self.graceful_shutdown = GracefulShutdown(self)
        self.status_task = None
        self.health_task = None
    
    async def setup_discord_bot(self):
        """設定 Discord Bot"""
        try:
            # 添加 discord-bot 目錄到路徑
            discord_path = os.path.join(os.path.dirname(__file__), 'discord-bot')
            if discord_path not in sys.path:
                sys.path.insert(0, discord_path)
            
            # 動態導入 Discord Bot
            from discord_bot_wrapper import DiscordBotWrapper
            self.discord_bot = DiscordBotWrapper()
            logger.info("✅ Discord Bot 設定完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ Discord Bot 設定失敗: {e}")
            self.bots_status['discord']['error'] = str(e)
            return False
    
    async def setup_twitch_bot(self):
        """設定 Twitch Bot"""
        try:
            # 添加 twitch-bot 目錄到路徑
            twitch_path = os.path.join(os.path.dirname(__file__), 'twitch-bot')
            if twitch_path not in sys.path:
                sys.path.insert(0, twitch_path)
            
            # 動態導入 Twitch Bot
            from twitch_bot_wrapper import TwitchBotWrapper
            self.twitch_bot = TwitchBotWrapper()
            logger.info("✅ Twitch Bot 設定完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ Twitch Bot 設定失敗: {e}")
            self.bots_status['twitch']['error'] = str(e)
            return False
    
    async def start_discord_bot(self):
        """啟動 Discord Bot"""
        if not self.discord_bot:
            if not await self.setup_discord_bot():
                return
        
        try:
            logger.info("🚀 正在啟動 Discord Bot...")
            self.bots_status['discord']['running'] = True
            await self.discord_bot.start()
            
        except Exception as e:
            logger.error(f"❌ Discord Bot 運行錯誤: {e}")
            self.bots_status['discord']['error'] = str(e)
            self.bots_status['discord']['running'] = False
    
    async def start_twitch_bot(self):
        """啟動 Twitch Bot"""
        if not self.twitch_bot:
            if not await self.setup_twitch_bot():
                return
        
        try:
            logger.info("🚀 正在啟動 Twitch Bot...")
            self.bots_status['twitch']['running'] = True
            await self.twitch_bot.start()
            
        except Exception as e:
            logger.error(f"❌ Twitch Bot 運行錯誤: {e}")
            self.bots_status['twitch']['error'] = str(e)
            self.bots_status['twitch']['running'] = False
    
    async def start_all_bots(self):
        """同時啟動所有 Bot"""
        logger.info("🎯 Niibot 統一啟動器開始運行")
        logger.info("📊 正在初始化 Bot 系統...")
        
        # 啟動系統監控
        self.status_task = asyncio.create_task(
            periodic_status_display(self, self.system_monitor, interval=300),  # 5分鐘更新一次
            name="StatusDisplay"
        )
        
        # 啟動健康檢查
        self.health_task = asyncio.create_task(
            self.health_checker.start_monitoring(),
            name="HealthChecker"
        )
        
        # 並行啟動兩個 Bot
        tasks = []
        
        # 創建 Discord Bot 任務
        self.discord_task = asyncio.create_task(
            self.start_discord_bot(), 
            name="DiscordBot"
        )
        tasks.append(self.discord_task)
        
        # 延遲 2 秒後啟動 Twitch Bot，避免資源競爭
        await asyncio.sleep(2)
        
        self.twitch_task = asyncio.create_task(
            self.start_twitch_bot(), 
            name="TwitchBot"
        )
        tasks.append(self.twitch_task)
        
        # 顯示初始狀態
        initial_status = create_status_display(self, self.system_monitor)
        logger.info(f"📊 初始狀態:\n{initial_status}")
        
        # 等待關閉信號或任一 Bot 完成
        done, pending = await asyncio.wait(
            tasks + [asyncio.create_task(self.shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        logger.info("📋 正在關閉 Bot 系統...")
        await self.graceful_shutdown.shutdown_sequence()
    
    async def shutdown_all(self):
        """關閉所有 Bot"""
        logger.info("🛑 正在關閉所有 Bot...")
        
        # 關閉監控任務
        if self.status_task and not self.status_task.done():
            self.status_task.cancel()
        
        if self.health_task and not self.health_task.done():
            self.health_task.cancel()
        
        # 關閉 Discord Bot
        if self.discord_bot and self.bots_status['discord']['running']:
            try:
                await self.discord_bot.close()
                self.bots_status['discord']['running'] = False
                logger.info("✅ Discord Bot 已關閉")
            except Exception as e:
                logger.error(f"❌ 關閉 Discord Bot 時發生錯誤: {e}")
        
        # 關閉 Twitch Bot
        if self.twitch_bot and self.bots_status['twitch']['running']:
            try:
                await self.twitch_bot.close()
                self.bots_status['twitch']['running'] = False
                logger.info("✅ Twitch Bot 已關閉")
            except Exception as e:
                logger.error(f"❌ 關閉 Twitch Bot 時發生錯誤: {e}")
        
        # 取消任務
        tasks_to_cancel = []
        if self.discord_task and not self.discord_task.done():
            tasks_to_cancel.append(self.discord_task)
        
        if self.twitch_task and not self.twitch_task.done():
            tasks_to_cancel.append(self.twitch_task)
        
        if tasks_to_cancel:
            for task in tasks_to_cancel:
                task.cancel()
            
            # 等待任務完成取消
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        
        # 關閉線程池
        self.executor.shutdown(wait=True)
        
        logger.info("🎯 所有 Bot 已安全關閉")
    
    def signal_handler(self, signum, frame):
        """處理系統信號"""
        logger.info(f"📡 接收到信號 {signum}，正在安全關閉...")
        self.shutdown_event.set()
    
    def get_status(self) -> Dict[str, Any]:
        """獲取 Bot 狀態"""
        discord_status = self.bots_status['discord'].copy()
        twitch_status = self.bots_status['twitch'].copy()
        
        # 添加詳細狀態信息
        if self.discord_bot:
            discord_status.update(self.discord_bot.status)
        
        if self.twitch_bot:
            twitch_status.update(self.twitch_bot.status)
        
        return {
            'discord': discord_status,
            'twitch': twitch_status,
            'system': self.system_monitor.get_system_info()
        }

def print_banner():
    """顯示啟動橫幅"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                         🤖 Niibot 2.0                        ║
║                    雙平台機器人統一啟動器                      ║
║                                                              ║
║  Discord Bot  ⚡  Twitch Bot  ⚡  統一管理                   ║
║                                                              ║
║     • 智能错誤恢復        • 系統監控                      ║
║     • 優雅關閉管理        • 健康檢查                      ║
╚══════════════════════════════════════════════════════════════╝
    """
    print(banner)
    print(f"🔍 Python 版本: {sys.version.split()[0]}")
    print(f"📍 工作目錄: {os.getcwd()}")
    print(f"🔄 啟動時間: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    logger.info("🚀 正在初始化 Niibot 統一啟動器...")

async def check_configuration():
    """檢查配置檔案和必要設定"""
    config_issues = []
    
    # 檢查 .env 檔案
    if not os.path.exists('.env'):
        config_issues.append("❌ 找不到 .env 配置檔案")
    
    # 檢查目錄結構
    required_dirs = ['discord-bot', 'twitch-bot']
    for dir_name in required_dirs:
        if not os.path.exists(dir_name):
            config_issues.append(f"❌ 找不到必要目錄: {dir_name}")
    
    # 檢查關鍵檔案
    critical_files = [
        'discord-bot/bot.py',
        'twitch-bot/bot_unified.py',
        'shared/config/unified_config.py'
    ]
    
    for file_path in critical_files:
        if not os.path.exists(file_path):
            config_issues.append(f"❌ 找不到關鍵檔案: {file_path}")
    
    if config_issues:
        logger.error("❌ 配置檢查失敗:")
        for issue in config_issues:
            logger.error(f"  {issue}")
        logger.info("💡 請確認所有必要檔案和目錄都存在")
        return False
    
    logger.info("✅ 配置檢查通過")
    return True

async def main():
    """主程式"""
    print_banner()
    
    # 檢查配置
    if not await check_configuration():
        sys.exit(1)
    
    # 創建 Bot 管理器
    bot_manager = BotManager()
    
    # 設定信號處理
    def signal_handler(signum, frame):
        logger.info(f"📡 接收到信號 {signum}，正在安全關閉...")
        bot_manager.shutdown_event.set()
    
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)
    if hasattr(signal, 'SIGINT'):
        signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # 啟動所有 Bot
        await bot_manager.start_all_bots()
        
    except KeyboardInterrupt:
        logger.info("⌨️ 接收到 Ctrl+C，正在關閉...")
    except Exception as e:
        logger.error(f"❌ 啟動過程發生未預期錯誤: {e}")
        import traceback
        traceback.print_exc()
    finally:
        logger.info("👋 Niibot 統一啟動器已退出")

if __name__ == "__main__":
    try:
        # 檢查 Python 版本
        if sys.version_info < (3, 8):
            print("❌ 錯誤: 需要 Python 3.8 或更高版本")
            print(f"ℹ️ 目前版本: {sys.version}")
            sys.exit(1)
        
        # 檢查必要的依賴套件
        try:
            import psutil
        except ImportError:
            logger.error("❌ 缺少必要的依賴套件: psutil")
            logger.info("💡 請執行: pip install psutil")
            sys.exit(1)
        
        # 運行主程式
        asyncio.run(main())
        
    except KeyboardInterrupt:
        logger.info("👋 程式被用戶中斷")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ 程式執行失敗: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)