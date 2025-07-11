import json
import os
import asyncio
import aiofiles
from typing import Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class SimpleDataManager:
    """簡化的資料管理器，專為 Twitch Bot 設計"""
    
    def __init__(self, data_path: str = "data"):
        self.data_path = data_path
        self.locks = {}  # 檔案鎖
        self._ensure_directory()
    
    def _ensure_directory(self):
        """確保資料目錄存在"""
        if not os.path.exists(self.data_path):
            os.makedirs(self.data_path)
    
    def _get_file_path(self, filename: str) -> str:
        """獲取檔案完整路徑"""
        return os.path.join(self.data_path, filename)
    
    def _get_lock(self, filename: str) -> asyncio.Lock:
        """獲取檔案鎖"""
        if filename not in self.locks:
            self.locks[filename] = asyncio.Lock()
        return self.locks[filename]
    
    async def read_json(self, filename: str, default: Dict[str, Any] = None) -> Dict[str, Any]:
        """讀取 JSON 檔案"""
        if default is None:
            default = {}
        
        filepath = self._get_file_path(filename)
        lock = self._get_lock(filename)
        
        async with lock:
            try:
                if not os.path.exists(filepath):
                    logger.info(f"檔案不存在，返回預設值: {filename}")
                    return default.copy()
                
                async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    if not content.strip():
                        logger.warning(f"檔案為空: {filename}")
                        return default.copy()
                    
                    data = json.loads(content)
                    logger.debug(f"成功讀取檔案: {filename}")
                    return data
                    
            except json.JSONDecodeError as e:
                logger.error(f"JSON 解析錯誤 {filename}: {e}")
                return default.copy()
            except Exception as e:
                logger.error(f"讀取檔案錯誤 {filename}: {e}")
                return default.copy()
    
    async def write_json(self, filename: str, data: Dict[str, Any]) -> bool:
        """寫入 JSON 檔案"""
        filepath = self._get_file_path(filename)
        lock = self._get_lock(filename)
        
        async with lock:
            try:
                # 添加更新時間戳
                if isinstance(data, dict) and 'metadata' not in data:
                    data['metadata'] = {}
                
                if isinstance(data, dict) and 'metadata' in data:
                    data['metadata']['last_updated'] = datetime.now().isoformat()
                
                # 創建備份 (簡化版)
                if os.path.exists(filepath):
                    backup_path = filepath + '.backup'
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                    os.rename(filepath, backup_path)
                
                # 寫入新檔案
                async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(data, ensure_ascii=False, indent=2))
                
                logger.debug(f"成功寫入檔案: {filename}")
                return True
                
            except Exception as e:
                logger.error(f"寫入檔案錯誤 {filename}: {e}")
                # 恢復備份
                backup_path = filepath + '.backup'
                if os.path.exists(backup_path):
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    os.rename(backup_path, filepath)
                return False
    
    async def update_json(self, filename: str, update_func, default: Dict[str, Any] = None) -> bool:
        """原子性更新 JSON 檔案"""
        if default is None:
            default = {}
        
        lock = self._get_lock(filename)
        
        async with lock:
            try:
                # 讀取現有資料
                data = await self.read_json(filename, default)
                
                # 應用更新函數
                updated_data = update_func(data)
                
                # 寫入更新後的資料
                success = await self.write_json(filename, updated_data)
                
                if success:
                    logger.debug(f"成功更新檔案: {filename}")
                else:
                    logger.error(f"更新檔案失敗: {filename}")
                
                return success
                
            except Exception as e:
                logger.error(f"更新檔案錯誤 {filename}: {e}")
                return False
    
    def file_exists(self, filename: str) -> bool:
        """檢查檔案是否存在"""
        filepath = self._get_file_path(filename)
        return os.path.exists(filepath)