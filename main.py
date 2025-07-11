#!/usr/bin/env python3
"""
Niibot 主啟動腳本
統一啟動 Discord Bot 和 Twitch Bot
"""

import sys
import os
import asyncio
import argparse
import logging

# 添加專案根目錄到Python路徑
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# 設定基本日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def parse_args():
    """解析命令列參數"""
    parser = argparse.ArgumentParser(description='Niibot 啟動器')
    parser.add_argument(
        'bot', 
        choices=['discord', 'twitch', 'both'],
        help='要啟動的機器人類型'
    )
    parser.add_argument(
        '--env',
        default='local',
        choices=['local', 'prod'],
        help='執行環境 (預設: local)'
    )
    return parser.parse_args()

def check_config():
    """檢查配置檔案是否存在"""
    config_files = [
        'config/shared/common.env',
        'config/discord/bot.env', 
        'config/discord/features.env',
        'config/twitch/bot.env',
        'config/twitch/features.env'
    ]
    
    missing_files = []
    for config_file in config_files:
        if not os.path.exists(config_file):
            missing_files.append(config_file)
    
    if missing_files:
        logger.error("缺少配置檔案:")
        for file in missing_files:
            logger.error(f"  - {file}")
        logger.info("請參考 .example 檔案創建配置檔案")
        return False
    
    return True

async def start_discord_bot():
    """啟動 Discord Bot"""
    try:
        logger.info("🤖 啟動 Discord Bot...")
        
        # 保存原始工作目錄
        original_cwd = os.getcwd()
        
        # 切換到 discord-bot 目錄
        discord_bot_path = os.path.join(project_root, 'discord-bot')
        os.chdir(discord_bot_path)
        
        # 添加專案根目錄到路徑以便導入 shared 模組
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        
        # 導入並執行Discord bot
        sys.path.insert(0, discord_bot_path)
        import bot
        await bot.main()
        
    except Exception as e:
        logger.error(f"❌ Discord Bot 啟動失敗: {e}")
        # 恢復原始工作目錄
        os.chdir(original_cwd)
        raise

async def start_twitch_bot():
    """啟動 Twitch Bot"""
    try:
        logger.info("🎮 啟動 Twitch Bot...")
        
        # 保存原始工作目錄
        original_cwd = os.getcwd()
        
        # 切換到 twitch-bot 目錄
        twitch_bot_path = os.path.join(project_root, 'twitch-bot')
        os.chdir(twitch_bot_path)
        
        # 添加專案根目錄到路徑以便導入 shared 模組
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        
        # 導入並執行Twitch bot
        sys.path.insert(0, twitch_bot_path) 
        from bot import TwitchBot
        bot = TwitchBot()
        await bot.start()  # 簡化後應該不會觸發 web 服務
        
    except Exception as e:
        logger.error(f"❌ Twitch Bot 啟動失敗: {e}")
        # 恢復原始工作目錄
        os.chdir(original_cwd)
        raise

async def start_both_bots():
    """同時啟動兩個機器人"""
    try:
        logger.info("🚀 同時啟動 Discord 和 Twitch Bot...")
        
        # 重設 sys.path 避免模組衝突
        original_path = sys.path.copy()
        
        # 創建任務
        discord_task = asyncio.create_task(start_discord_bot())
        
        # 重設路徑以避免衝突
        sys.path = original_path.copy()
        
        twitch_task = asyncio.create_task(start_twitch_bot())
        
        # 等待任務完成
        await asyncio.gather(discord_task, twitch_task)
        
    except Exception as e:
        logger.error(f"❌ 啟動失敗: {e}")
        raise

def main():
    """主函數"""
    args = parse_args()
    
    # 設定環境變數
    os.environ['BOT_ENV'] = args.env
    logger.info(f"🌍 環境設定: {args.env}")
    
    # 檢查配置
    if not check_config():
        sys.exit(1)
    
    # 根據參數啟動對應的機器人
    try:
        if args.bot == 'discord':
            asyncio.run(start_discord_bot())
        elif args.bot == 'twitch':
            asyncio.run(start_twitch_bot())
        elif args.bot == 'both':
            asyncio.run(start_both_bots())
    except KeyboardInterrupt:
        logger.info("👋 接收到中斷信號，正在關閉...")
    except Exception as e:
        logger.error(f"💥 執行錯誤: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()