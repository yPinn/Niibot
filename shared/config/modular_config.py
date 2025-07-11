"""
Niibot 模組化配置管理器
統一管理 Discord Bot、Twitch Bot 和共用配置
"""

import os
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass


@dataclass
class ConfigModule:
    """配置模組定義"""
    name: str
    file_path: str
    prefix: str = ""


class ModularConfigManager:
    """模組化配置管理器"""
    
    def __init__(self, base_path: str = None):
        """
        初始化配置管理器
        
        Args:
            base_path: 配置文件基礎路徑，預設為專案根目錄
        """
        if base_path is None:
            # 自動檢測專案根目錄
            current_file = Path(__file__)
            self.base_path = current_file.parent.parent.parent
        else:
            self.base_path = Path(base_path)
        
        self.config_dir = self.base_path / "config"
        self._config_data: Dict[str, Any] = {}
        self._loaded_modules: List[str] = []
        
        # 定義配置模組
        self.modules = {
            "shared": ConfigModule("shared", "shared/common.env"),
            "discord_bot": ConfigModule("discord_bot", "discord/bot.env", "DISCORD_"),
            "discord_features": ConfigModule("discord_features", "discord/features.env", "DISCORD_"),
            "twitch_bot": ConfigModule("twitch_bot", "twitch/bot.env", "TWITCH_"),
            "twitch_features": ConfigModule("twitch_features", "twitch/features.env", "TWITCH_")
        }
        
        # 根據環境自動載入配置
        self._auto_load_configs()
    
    def _auto_load_configs(self):
        """自動載入所有配置模組"""
        # 始終載入共用配置
        self.load_module("shared")
        
        # 根據需要載入其他模組
        # 這裡可以根據環境變數或其他邏輯決定載入哪些模組
        bot_env = os.getenv("BOT_ENV", "local")
        
        # 載入 Discord 配置
        self.load_module("discord_bot")
        self.load_module("discord_features")
        
        # 載入 Twitch 配置
        self.load_module("twitch_bot")
        self.load_module("twitch_features")
    
    def load_module(self, module_name: str) -> bool:
        """
        載入指定配置模組
        
        Args:
            module_name: 模組名稱
            
        Returns:
            bool: 載入是否成功
        """
        if module_name not in self.modules:
            logging.warning(f"Unknown config module: {module_name}")
            return False
        
        module = self.modules[module_name]
        config_file = self.config_dir / module.file_path
        
        if not config_file.exists():
            logging.warning(f"Config file not found: {config_file}")
            return False
        
        try:
            self._load_env_file(config_file, module.prefix)
            self._loaded_modules.append(module_name)
            logging.info(f"Loaded config module: {module_name}")
            return True
        except Exception as e:
            logging.error(f"Failed to load config module {module_name}: {e}")
            return False
    
    def _load_env_file(self, file_path: Path, prefix: str = ""):
        """
        載入 .env 檔案
        
        Args:
            file_path: 檔案路徑
            prefix: 環境變數前綴
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # 跳過註解和空行
                if not line or line.startswith('#'):
                    continue
                
                # 解析環境變數
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # 移除引號
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    # 添加前綴（如果需要）
                    env_key = f"{prefix}{key}" if prefix else key
                    
                    # 設定環境變數（如果尚未設定）
                    if env_key not in os.environ:
                        os.environ[env_key] = value
                    
                    # 儲存到內部配置
                    self._config_data[env_key] = value
    
    def get(self, key: str, default: Any = None, module: str = None) -> Any:
        """
        取得配置值
        
        Args:
            key: 配置鍵名
            default: 預設值
            module: 指定模組（可選）
            
        Returns:
            配置值
        """
        # 如果指定模組，添加前綴
        if module:
            if module in ["discord_bot", "discord_features"]:
                key = f"DISCORD_{key}"
            elif module in ["twitch_bot", "twitch_features"]:
                key = f"TWITCH_{key}"
        
        # 優先從環境變數取得
        value = os.getenv(key)
        if value is not None:
            return self._convert_value(value)
        
        # 從內部配置取得
        value = self._config_data.get(key, default)
        return self._convert_value(value) if value is not None else default
    
    def _convert_value(self, value: str) -> Any:
        """
        轉換配置值類型
        
        Args:
            value: 字串值
            
        Returns:
            轉換後的值
        """
        if isinstance(value, str):
            # 布林值轉換
            if value.lower() in ('true', 'yes', '1', 'on'):
                return True
            elif value.lower() in ('false', 'no', '0', 'off'):
                return False
            
            # 數字轉換
            try:
                if '.' in value:
                    return float(value)
                else:
                    return int(value)
            except ValueError:
                pass
            
            # 列表轉換（逗號分隔）
            if ',' in value:
                return [item.strip() for item in value.split(',') if item.strip()]
        
        return value
    
    def get_discord_config(self, key: str, default: Any = None) -> Any:
        """取得 Discord 配置"""
        return self.get(f"DISCORD_{key}", default)
    
    def get_twitch_config(self, key: str, default: Any = None) -> Any:
        """取得 Twitch 配置"""
        return self.get(f"TWITCH_{key}", default)
    
    def get_shared_config(self, key: str, default: Any = None) -> Any:
        """取得共用配置"""
        return self.get(key, default)
    
    def list_loaded_modules(self) -> List[str]:
        """列出已載入的模組"""
        return self._loaded_modules.copy()
    
    def reload_module(self, module_name: str) -> bool:
        """重新載入指定模組"""
        if module_name in self._loaded_modules:
            self._loaded_modules.remove(module_name)
        return self.load_module(module_name)
    
    def get_config_summary(self) -> Dict[str, Any]:
        """取得配置摘要（隱藏敏感資訊）"""
        summary = {}
        sensitive_keys = ['TOKEN', 'SECRET', 'KEY', 'PASSWORD', 'BEARER']
        
        for key, value in self._config_data.items():
            if any(sensitive in key.upper() for sensitive in sensitive_keys):
                summary[key] = "***隱藏***"
            else:
                summary[key] = value
        
        return summary
    
    @property
    def data_dir(self) -> str:
        """取得資料目錄路徑 (相容性屬性)"""
        return self.get_shared_config('DATA_DIR', 'shared/data')
    
    @property 
    def use_keep_alive(self) -> bool:
        """是否使用 keep_alive (相容性屬性)"""
        return self.get_discord_config('USE_KEEP_ALIVE', False)
    
    @property
    def token(self) -> str:
        """取得 Discord Token (相容性屬性)"""
        return self.get_discord_config('TOKEN', '')
    
    @property
    def activity_type(self) -> str:
        """取得活動類型 (相容性屬性)"""
        return self.get_discord_config('ACTIVITY_TYPE', 'playing')
    
    @property
    def activity_name(self) -> str:
        """取得活動名稱 (相容性屬性)"""
        return self.get_discord_config('ACTIVITY_NAME', '')
    
    @property
    def activity_url(self) -> str:
        """取得活動URL (相容性屬性)"""
        return self.get_discord_config('ACTIVITY_URL', '')
    
    @property
    def status(self) -> str:
        """取得機器人狀態 (相容性屬性)"""
        return self.get_discord_config('STATUS', 'online')


# 創建全域實例
config = ModularConfigManager()


# 相容性函數
def get_config():
    """取得配置管理器實例（相容性函數）"""
    return config