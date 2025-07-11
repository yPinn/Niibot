#!/usr/bin/env python3
"""
Niibot 統一啟動腳本
提供便捷的啟動選項和模式選擇
"""

import argparse
import asyncio
import sys
import os
import logging

# 設定日誌級別
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('NiibotStarter')

def parse_arguments():
    """解析命令行參數"""
    parser = argparse.ArgumentParser(description="Niibot 統一啟動器")
    
    parser.add_argument(
        '--mode', 
        choices=['unified', 'discord-only', 'twitch-only'], 
        default='unified',
        help='啟動模式 (預設: unified)'
    )
    
    parser.add_argument(
        '--config-check', 
        action='store_true',
        help='只檢查配置，不啟動 bot'
    )
    
    parser.add_argument(
        '--status', 
        action='store_true',
        help='顯示系統狀態'
    )
    
    parser.add_argument(
        '--log-level', 
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], 
        default='INFO',
        help='日誌級別 (預設: INFO)'
    )
    
    return parser.parse_args()

async def check_only():
    """只檢查配置"""
    from app import check_configuration
    result = await check_configuration()
    if result:
        logger.info("✅ 配置檢查通過，可以啟動 bot")
        return True
    else:
        logger.error("❌ 配置檢查失敗，請修復後重試")
        return False

async def show_status():
    """顯示系統狀態"""
    from launcher_utils import SystemMonitor, create_status_display
    
    class MockBotManager:
        def __init__(self):
            self.bots_status = {
                'discord': {'running': False, 'error': None},
                'twitch': {'running': False, 'error': None}
            }
        
        def get_status(self):
            return self.bots_status
    
    monitor = SystemMonitor()
    mock_manager = MockBotManager()
    
    status_display = create_status_display(mock_manager, monitor)
    print(status_display)
    
    system_info = monitor.get_system_info()
    print("\n🔍 詳細系統信息:")
    print(f"  CPU 使用率: {system_info.get('cpu_usage', 0):.1f}%")
    print(f"  記憶體使用率: {system_info.get('memory_usage', 0):.1f}%")
    print(f"  可用記憶體: {system_info.get('memory_available', 0) / 1024 / 1024 / 1024:.1f} GB")
    print(f"  Python 版本: {sys.version.split()[0]}")
    print(f"  工作目錄: {os.getcwd()}")

async def start_discord_only():
    """只啟動 Discord Bot"""
    logger.info("🔵 啟動 Discord Bot 專用模式")
    
    try:
        from discord_bot_wrapper import DiscordBotWrapper
        
        wrapper = DiscordBotWrapper()
        await wrapper.start()
        
    except Exception as e:
        logger.error(f"❌ Discord Bot 啟動失敗: {e}")
        return False
    
    return True

async def start_twitch_only():
    """只啟動 Twitch Bot"""
    logger.info("🟣 啟動 Twitch Bot 專用模式")
    
    try:
        from twitch_bot_wrapper import TwitchBotWrapper
        
        wrapper = TwitchBotWrapper()
        await wrapper.start()
        
    except Exception as e:
        logger.error(f"❌ Twitch Bot 啟動失敗: {e}")
        return False
    
    return True

async def start_unified():
    """啟動統一模式"""
    logger.info("🤖 啟動統一模式")
    
    try:
        from app import main
        await main()
        
    except Exception as e:
        logger.error(f"❌ 統一啟動器啟動失敗: {e}")
        return False
    
    return True

async def main():
    """主程式"""
    args = parse_arguments()
    
    # 設定日誌級別
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # 根據參數執行相應功能
    if args.config_check:
        success = await check_only()
        sys.exit(0 if success else 1)
    
    if args.status:
        await show_status()
        sys.exit(0)
    
    # 啟動對應模式
    if args.mode == 'discord-only':
        success = await start_discord_only()
    elif args.mode == 'twitch-only':
        success = await start_twitch_only()
    else:  # unified
        success = await start_unified()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 程式被用戶中斷")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ 程式執行失敗: {e}")
        sys.exit(1)