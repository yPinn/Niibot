"""
啟動器工具模組
提供狀態監控、健康檢查和系統管理功能
"""

import asyncio
import psutil
import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger('LauncherUtils')

class SystemMonitor:
    """系統監控器"""
    
    def __init__(self):
        self.start_time = time.time()
        self.last_check = None
    
    def get_system_info(self) -> Dict[str, Any]:
        """獲取系統資訊"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            return {
                'cpu_usage': cpu_percent,
                'memory_usage': memory.percent,
                'memory_available': memory.available,
                'uptime': time.time() - self.start_time,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.warning(f"無法獲取系統資訊: {e}")
            return {
                'uptime': time.time() - self.start_time,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

class HealthChecker:
    """健康檢查器"""
    
    def __init__(self, bot_manager):
        self.bot_manager = bot_manager
        self.check_interval = 30  # 30秒檢查一次
        self.max_restart_attempts = 3
        self.restart_counts = {'discord': 0, 'twitch': 0}
    
    async def start_monitoring(self):
        """開始健康監控"""
        logger.info("🔍 健康監控器啟動")
        
        while not self.bot_manager.shutdown_event.is_set():
            try:
                await self.perform_health_check()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康檢查發生錯誤: {e}")
                await asyncio.sleep(5)
    
    async def perform_health_check(self):
        """執行健康檢查"""
        status = self.bot_manager.get_status()
        
        for bot_name, bot_status in status.items():
            if bot_status.get('error') and self.restart_counts[bot_name] < self.max_restart_attempts:
                logger.warning(f"⚠️ 檢測到 {bot_name} Bot 錯誤，嘗試重啟...")
                await self.attempt_restart(bot_name)
    
    async def attempt_restart(self, bot_name: str):
        """嘗試重啟 Bot"""
        try:
            self.restart_counts[bot_name] += 1
            logger.info(f"🔄 嘗試重啟 {bot_name} Bot (第 {self.restart_counts[bot_name]} 次)")
            
            if bot_name == 'discord':
                await self.bot_manager.start_discord_bot()
            elif bot_name == 'twitch':
                await self.bot_manager.start_twitch_bot()
            
            logger.info(f"✅ {bot_name} Bot 重啟成功")
            
        except Exception as e:
            logger.error(f"❌ {bot_name} Bot 重啟失敗: {e}")

class GracefulShutdown:
    """優雅關閉管理器"""
    
    def __init__(self, bot_manager):
        self.bot_manager = bot_manager
        self.shutdown_timeout = 30  # 30秒超時
    
    async def shutdown_sequence(self):
        """執行關閉序列"""
        logger.info("🛑 開始優雅關閉序列...")
        
        start_time = time.time()
        
        try:
            # 階段 1: 設定關閉信號
            self.bot_manager.shutdown_event.set()
            logger.info("📡 關閉信號已發送")
            
            # 階段 2: 等待 Bot 自然關閉
            await asyncio.sleep(2)
            
            # 階段 3: 強制關閉 Bot
            await self.bot_manager.shutdown_all()
            
            # 階段 4: 清理資源
            await self.cleanup_resources()
            
            elapsed = time.time() - start_time
            logger.info(f"✅ 優雅關閉完成 (耗時: {elapsed:.2f}秒)")
            
        except Exception as e:
            logger.error(f"❌ 關閉過程發生錯誤: {e}")
        
        finally:
            # 確保所有任務都被取消
            await self.cancel_remaining_tasks()
    
    async def cleanup_resources(self):
        """清理資源"""
        try:
            # 清理日誌處理器
            logging.shutdown()
            
            # 其他清理工作...
            logger.info("🧹 資源清理完成")
            
        except Exception as e:
            logger.warning(f"資源清理警告: {e}")
    
    async def cancel_remaining_tasks(self):
        """取消剩餘任務"""
        try:
            # 獲取當前事件循環中的所有任務
            current_task = asyncio.current_task()
            tasks = [t for t in asyncio.all_tasks() if not t.done() and t != current_task]
            
            if tasks:
                logger.info(f"🔄 取消 {len(tasks)} 個剩餘任務...")
                
                # 標記所有任務為取消，但不等待
                for task in tasks:
                    if not task.cancelled():
                        task.cancel()
                
                # 簡短等待讓任務有機會清理
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*tasks, return_exceptions=True),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("⚠️ 部分任務取消超時，強制繼續")
                
                logger.info("✅ 所有任務已取消")
            
        except Exception as e:
            logger.warning(f"任務取消警告: {e}")

def create_status_display(bot_manager, system_monitor) -> str:
    """創建狀態顯示"""
    try:
        status = bot_manager.get_status()
        system_info = system_monitor.get_system_info()
        
        discord_status = "🟢 運行中" if status['discord']['running'] else "🔴 離線"
        twitch_status = "🟢 運行中" if status['twitch']['running'] else "🔴 離線"
        
        uptime_mins = int(system_info.get('uptime', 0) / 60)
        
        display = f"""
╔════════════════════════════════════════════════════════════╗
║                    🤖 Niibot 狀態面板                      ║
╠════════════════════════════════════════════════════════════╣
║ Discord Bot: {discord_status:<15} Twitch Bot: {twitch_status:<15} ║
║ 運行時間: {uptime_mins:>3} 分鐘                                  ║
║ CPU 使用率: {system_info.get('cpu_usage', 0):>5.1f}%                           ║
║ 記憶體使用率: {system_info.get('memory_usage', 0):>5.1f}%                       ║
╚════════════════════════════════════════════════════════════╝
        """
        
        return display.strip()
        
    except Exception as e:
        return f"❌ 狀態顯示錯誤: {e}"

async def periodic_status_display(bot_manager, system_monitor, interval=60):
    """定期顯示狀態"""
    while not bot_manager.shutdown_event.is_set():
        try:
            status_display = create_status_display(bot_manager, system_monitor)
            logger.info(f"📊 狀態更新:\n{status_display}")
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"狀態顯示錯誤: {e}")
            await asyncio.sleep(10)