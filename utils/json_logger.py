import json
import logging
import os
from datetime import datetime
from typing import Dict, Any
import asyncio
import aiofiles


class JSONFormatter(logging.Formatter):
    """JSON 格式的日誌格式器"""
    
    def format(self, record: logging.LogRecord) -> str:
        # 基本日誌資訊
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # 添加額外資訊
        if hasattr(record, 'user_id'):
            log_entry['user_id'] = record.user_id
        if hasattr(record, 'guild_id'):
            log_entry['guild_id'] = record.guild_id
        if hasattr(record, 'command_name'):
            log_entry['command_name'] = record.command_name
        if hasattr(record, 'error_type'):
            log_entry['error_type'] = record.error_type
        
        # 處理異常資訊
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': self.formatException(record.exc_info)
            }
        
        return json.dumps(log_entry, ensure_ascii=False, separators=(',', ':'))


class AsyncJSONFileHandler(logging.Handler):
    """非同步 JSON 檔案處理器"""
    
    def __init__(self, filename: str, max_size: int = 10 * 1024 * 1024):  # 10MB
        super().__init__()
        self.filename = filename
        self.max_size = max_size
        self._write_queue = asyncio.Queue()
        self._writer_task = None
        self._ensure_directory()
        
    def _ensure_directory(self):
        """確保日誌目錄存在"""
        directory = os.path.dirname(self.filename)
        if directory:
            os.makedirs(directory, exist_ok=True)
    
    def emit(self, record: logging.LogRecord):
        """發送日誌記錄"""
        try:
            msg = self.format(record)
            # 非同步寫入
            if self._write_queue:
                try:
                    self._write_queue.put_nowait(msg)
                except asyncio.QueueFull:
                    # 佇列滿了，丟棄舊的日誌
                    pass
                
                # 啟動寫入任務
                if not self._writer_task or self._writer_task.done():
                    try:
                        loop = asyncio.get_event_loop()
                        self._writer_task = loop.create_task(self._async_writer())
                    except RuntimeError:
                        # 沒有事件循環，改用同步寫入
                        self._sync_write(msg)
        except Exception:
            self.handleError(record)
    
    def _sync_write(self, msg: str):
        """同步寫入（備用方案）"""
        try:
            with open(self.filename, 'a', encoding='utf-8') as f:
                f.write(msg + '\n')
        except Exception:
            pass
    
    async def _async_writer(self):
        """非同步寫入任務"""
        try:
            # 收集一批日誌進行寫入
            messages = []
            while True:
                try:
                    # 等待新訊息，最多等待 0.5 秒
                    msg = await asyncio.wait_for(self._write_queue.get(), timeout=0.5)
                    messages.append(msg)
                    
                    # 如果佇列還有更多訊息，繼續收集（最多 50 條）
                    while not self._write_queue.empty() and len(messages) < 50:
                        messages.append(self._write_queue.get_nowait())
                    
                    # 寫入檔案
                    await self._write_messages(messages)
                    messages.clear()
                    
                except asyncio.TimeoutError:
                    # 超時，寫入現有訊息
                    if messages:
                        await self._write_messages(messages)
                        messages.clear()
                    break
                except Exception:
                    break
        except Exception:
            pass
    
    async def _write_messages(self, messages: list):
        """批次寫入訊息"""
        if not messages:
            return
            
        try:
            # 檢查檔案大小
            if os.path.exists(self.filename) and os.path.getsize(self.filename) > self.max_size:
                await self._rotate_file()
            
            # 寫入檔案
            async with aiofiles.open(self.filename, 'a', encoding='utf-8') as f:
                for msg in messages:
                    await f.write(msg + '\n')
                await f.flush()
        except Exception:
            pass
    
    async def _rotate_file(self):
        """輪轉日誌檔案"""
        try:
            base_name = self.filename.rsplit('.', 1)[0]
            extension = '.json'
            
            # 移動舊檔案
            old_filename = f"{base_name}.old{extension}"
            if os.path.exists(old_filename):
                os.remove(old_filename)
            if os.path.exists(self.filename):
                os.rename(self.filename, old_filename)
        except Exception:
            pass


class JSONLogger:
    """JSON 日誌管理器"""
    
    @staticmethod
    def setup_json_logging(logger: logging.Logger, filename: str = None) -> bool:
        """設定 JSON 日誌記錄
        
        Args:
            logger: 要設定的日誌器
            filename: JSON 日誌檔案路徑
            
        Returns:
            bool: 設定是否成功
        """
        if not filename:
            return False
            
        try:
            # 創建 JSON 處理器
            json_handler = AsyncJSONFileHandler(filename)
            json_handler.setFormatter(JSONFormatter())
            
            # 設定為與主要日誌器相同的級別
            json_handler.setLevel(logger.level)
            
            # 添加到日誌器
            logger.addHandler(json_handler)
            
            return True
        except Exception:
            return False
    
    @staticmethod
    def parse_json_logs(filename: str, limit: int = 100) -> list:
        """解析 JSON 日誌檔案
        
        Args:
            filename: JSON 日誌檔案路徑
            limit: 最大讀取條數
            
        Returns:
            list: 日誌記錄列表
        """
        logs = []
        if not os.path.exists(filename):
            return logs
            
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                # 讀取最後 N 行
                for line in lines[-limit:]:
                    try:
                        log_entry = json.loads(line.strip())
                        logs.append(log_entry)
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
            
        return logs
    
    @staticmethod
    def get_log_stats(filename: str) -> Dict[str, Any]:
        """獲取日誌統計資訊
        
        Args:
            filename: JSON 日誌檔案路徑
            
        Returns:
            dict: 統計資訊
        """
        stats = {
            'total_logs': 0,
            'by_level': {},
            'by_module': {},
            'recent_errors': [],
            'file_size': 0,
            'last_modified': None
        }
        
        if not os.path.exists(filename):
            return stats
            
        try:
            # 檔案資訊
            file_stat = os.stat(filename)
            stats['file_size'] = file_stat.st_size
            stats['last_modified'] = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            
            # 分析日誌內容
            with open(filename, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        log_entry = json.loads(line.strip())
                        stats['total_logs'] += 1
                        
                        # 按級別統計
                        level = log_entry.get('level', 'UNKNOWN')
                        stats['by_level'][level] = stats['by_level'].get(level, 0) + 1
                        
                        # 按模組統計
                        module = log_entry.get('module', 'unknown')
                        stats['by_module'][module] = stats['by_module'].get(module, 0) + 1
                        
                        # 收集最近的錯誤
                        if level in ['ERROR', 'CRITICAL'] and len(stats['recent_errors']) < 10:
                            stats['recent_errors'].append({
                                'timestamp': log_entry.get('timestamp'),
                                'message': log_entry.get('message'),
                                'module': module
                            })
                            
                    except json.JSONDecodeError:
                        continue
                        
        except Exception:
            pass
            
        return stats