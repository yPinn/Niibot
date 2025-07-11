"""
Niibot 統一資料管理器
統一管理所有平台的資料存取
"""

import json
import os
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
import asyncio
import aiofiles


class UnifiedDataManager:
    """統一資料管理器"""
    
    def __init__(self, base_path: str = None):
        """
        初始化資料管理器
        
        Args:
            base_path: 資料目錄基礎路徑，預設為 shared/data
        """
        if base_path is None:
            current_file = Path(__file__)
            self.base_path = current_file.parent.parent / "data"
        else:
            self.base_path = Path(base_path)
        
        # 確保資料目錄存在
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger(__name__)
    
    def _get_file_path(self, filename: str) -> Path:
        """取得檔案完整路徑"""
        return self.base_path / filename
    
    async def load_json(self, filename: str, default: Any = None) -> Any:
        """
        異步載入 JSON 檔案
        
        Args:
            filename: 檔案名稱
            default: 預設值（當檔案不存在時）
            
        Returns:
            JSON 資料
        """
        file_path = self._get_file_path(filename)
        
        if not file_path.exists():
            self.logger.info(f"檔案不存在，使用預設值: {filename}")
            return default if default is not None else {}
        
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                if not content.strip():
                    self.logger.warning(f"檔案內容為空: {filename}")
                    return default if default is not None else {}
                
                data = json.loads(content)
                self.logger.debug(f"成功載入檔案: {filename}")
                return data
                
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON 格式錯誤 {filename}: {e}")
            return default if default is not None else {}
        except Exception as e:
            self.logger.error(f"載入檔案失敗 {filename}: {e}")
            return default if default is not None else {}
    
    async def save_json(self, filename: str, data: Any, backup: bool = True) -> bool:
        """
        異步儲存 JSON 檔案
        
        Args:
            filename: 檔案名稱
            data: 要儲存的資料
            backup: 是否建立備份
            
        Returns:
            bool: 儲存是否成功
        """
        file_path = self._get_file_path(filename)
        
        try:
            # 建立備份
            if backup and file_path.exists():
                backup_path = file_path.with_suffix(f".bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                try:
                    backup_path.write_bytes(file_path.read_bytes())
                except Exception as e:
                    self.logger.warning(f"建立備份失敗 {filename}: {e}")
            
            # 儲存檔案
            json_str = json.dumps(data, ensure_ascii=False, indent=2)
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(json_str)
            
            self.logger.debug(f"成功儲存檔案: {filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"儲存檔案失敗 {filename}: {e}")
            return False
    
    def load_json_sync(self, filename: str, default: Any = None) -> Any:
        """
        同步載入 JSON 檔案
        
        Args:
            filename: 檔案名稱
            default: 預設值
            
        Returns:
            JSON 資料
        """
        file_path = self._get_file_path(filename)
        
        if not file_path.exists():
            self.logger.info(f"檔案不存在，使用預設值: {filename}")
            return default if default is not None else {}
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content.strip():
                    self.logger.warning(f"檔案內容為空: {filename}")
                    return default if default is not None else {}
                
                data = json.loads(content)
                self.logger.debug(f"成功載入檔案: {filename}")
                return data
                
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON 格式錯誤 {filename}: {e}")
            return default if default is not None else {}
        except Exception as e:
            self.logger.error(f"載入檔案失敗 {filename}: {e}")
            return default if default is not None else {}
    
    def save_json_sync(self, filename: str, data: Any, backup: bool = True) -> bool:
        """
        同步儲存 JSON 檔案
        
        Args:
            filename: 檔案名稱
            data: 要儲存的資料
            backup: 是否建立備份
            
        Returns:
            bool: 儲存是否成功
        """
        file_path = self._get_file_path(filename)
        
        try:
            # 建立備份
            if backup and file_path.exists():
                backup_path = file_path.with_suffix(f".bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                try:
                    backup_path.write_bytes(file_path.read_bytes())
                except Exception as e:
                    self.logger.warning(f"建立備份失敗 {filename}: {e}")
            
            # 儲存檔案
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            self.logger.debug(f"成功儲存檔案: {filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"儲存檔案失敗 {filename}: {e}")
            return False
    
    # 便利方法
    async def load_eat_data(self) -> Dict[str, Any]:
        """載入用餐資料"""
        return await self.load_json("eat.json", {
            "主餐": [],
            "小吃": [],
            "點心": [],
            "飲料": []
        })
    
    async def save_eat_data(self, data: Dict[str, Any]) -> bool:
        """儲存用餐資料"""
        return await self.save_json("eat.json", data)
    
    async def load_draw_history(self) -> Dict[str, Any]:
        """載入抽獎記錄"""
        return await self.load_json("draw_history.json", {
            "records": []
        })
    
    async def save_draw_history(self, data: Dict[str, Any]) -> bool:
        """儲存抽獎記錄"""
        return await self.save_json("draw_history.json", data)
    
    def get_data_path(self) -> str:
        """取得資料目錄路徑"""
        return str(self.base_path)
    
    def cleanup_backups(self, keep_days: int = 7) -> int:
        """
        清理過期備份檔案
        
        Args:
            keep_days: 保留天數
            
        Returns:
            int: 清理的檔案數量
        """
        cutoff_time = datetime.now().timestamp() - (keep_days * 24 * 3600)
        cleaned_count = 0
        
        try:
            for backup_file in self.base_path.glob("*.bak.*"):
                if backup_file.stat().st_mtime < cutoff_time:
                    backup_file.unlink()
                    cleaned_count += 1
                    
            if cleaned_count > 0:
                self.logger.info(f"清理了 {cleaned_count} 個過期備份檔案")
                
        except Exception as e:
            self.logger.error(f"清理備份檔案失敗: {e}")
        
        return cleaned_count


# 建立全域實例
data_manager = UnifiedDataManager()


# 相容性函數
def get_data_manager():
    """取得資料管理器實例（相容性函數）"""
    return data_manager