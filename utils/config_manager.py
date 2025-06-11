import os
from typing import Any, List, Optional
from utils.logger import BotLogger

class ConfigManager:
    """統一的配置管理系統"""
    
    _instance = None
    _config = {}
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._load_config()
            ConfigManager._initialized = True
    
    def _load_config(self):
        """載入配置"""
        env = os.getenv("BOT_ENV", "local")
        
        try:
            if env == "prod":
                from config_prod import (
                    TOKEN, STATUS, ACTIVITY_TYPE, ACTIVITY_NAME, 
                    USE_KEEP_ALIVE, COMMAND_PREFIX
                )
                activity_url = getattr(__import__('config_prod'), 'ACTIVITY_URL', None)
            else:
                from config_local import (
                    TOKEN, STATUS, ACTIVITY_TYPE, ACTIVITY_NAME, 
                    USE_KEEP_ALIVE, COMMAND_PREFIX
                )
                activity_url = getattr(__import__('config_local'), 'ACTIVITY_URL', None)
            
            self._config = {
                'TOKEN': TOKEN,
                'STATUS': STATUS,
                'ACTIVITY_TYPE': ACTIVITY_TYPE,
                'ACTIVITY_NAME': ACTIVITY_NAME,
                'ACTIVITY_URL': activity_url,
                'USE_KEEP_ALIVE': USE_KEEP_ALIVE,
                'COMMAND_PREFIX': COMMAND_PREFIX,
                'BOT_ENV': env,
                
                # 從環境變數或預設值載入其他配置
                'TARGET_ROLE_ID': int(os.getenv('TARGET_ROLE_ID', '1378242954929639514')),
                'WORK_HOURS': int(os.getenv('WORK_HOURS', '9')),
                'DRAW_COOLDOWN': int(os.getenv('DRAW_COOLDOWN', '30')),
                'MAX_QUEUE_SIZE': int(os.getenv('MAX_QUEUE_SIZE', '50')),
                'DEFAULT_TEAMS': int(os.getenv('DEFAULT_TEAMS', '2')),
                'LOG_LEVEL': os.getenv('LOG_LEVEL', 'INFO'),
                'LOG_FILE': os.getenv('LOG_FILE', None),  # 生產環境不寫入檔案，避免權限問題
                'DATA_DIR': os.getenv('DATA_DIR', 'data'),
                'EMOJI_SAVE_INTERVAL': int(os.getenv('EMOJI_SAVE_INTERVAL', '30')),
                'REMINDER_CLEANUP_HOURS': int(os.getenv('REMINDER_CLEANUP_HOURS', '24')),
            }
            
            BotLogger.system_event("配置載入", f"環境: {env}, 配置項目數: {len(self._config)}")
            
        except ImportError as e:
            BotLogger.critical("ConfigManager", f"無法載入配置檔案 (環境: {env})", e)
            raise
        except Exception as e:
            BotLogger.error("ConfigManager", f"配置載入錯誤 (環境: {env})", e)
            raise
    
    def get(self, key: str, default: Any = None) -> Any:
        """取得配置值
        
        Args:
            key: 配置鍵值
            default: 預設值
            
        Returns:
            配置值或預設值
        """
        value = self._config.get(key, default)
        if value is None and default is None:
            BotLogger.warning("ConfigManager", f"配置項目 '{key}' 不存在且無預設值")
        return value
    
    def get_required(self, key: str) -> Any:
        """取得必要的配置值，若不存在則拋出異常
        
        Args:
            key: 配置鍵值
            
        Returns:
            配置值
            
        Raises:
            ValueError: 當配置項目不存在時
        """
        if key not in self._config or self._config[key] is None:
            BotLogger.error("ConfigManager", f"必要配置項目 '{key}' 遺失")
            raise ValueError(f"必要配置項目 '{key}' 遺失")
        return self._config[key]
    
    def set(self, key: str, value: Any):
        """設定配置值（僅限運行時修改）
        
        Args:
            key: 配置鍵值
            value: 配置值
        """
        old_value = self._config.get(key)
        self._config[key] = value
        BotLogger.info("ConfigManager", f"配置項目 '{key}' 已更新: {old_value} -> {value}")
    
    def get_all(self) -> dict:
        """取得所有配置（去除敏感資訊）"""
        safe_config = self._config.copy()
        if 'TOKEN' in safe_config:
            safe_config['TOKEN'] = '*' * 8  # 隱藏 token
        return safe_config
    
    @property
    def token(self) -> str:
        """Discord bot token"""
        return self.get_required('TOKEN')
    
    @property
    def status(self) -> str:
        """Bot 狀態"""
        return self.get('STATUS', 'online')
    
    @property
    def activity_type(self) -> str:
        """活動類型"""
        return self.get('ACTIVITY_TYPE', 'playing')
    
    @property
    def activity_name(self) -> str:
        """活動名稱"""
        return self.get('ACTIVITY_NAME', 'Discord Bot')
    
    @property
    def activity_url(self) -> Optional[str]:
        """活動 URL（僅串流需要）"""
        return self.get('ACTIVITY_URL')
    
    @property
    def use_keep_alive(self) -> bool:
        """是否使用保持連線"""
        return self.get('USE_KEEP_ALIVE', False)
    
    @property
    def command_prefix(self) -> List[str]:
        """指令前綴"""
        return self.get('COMMAND_PREFIX', ['?'])
    
    @property
    def target_role_id(self) -> int:
        """目標身分組 ID"""
        return self.get('TARGET_ROLE_ID', 0)
    
    @property
    def work_hours(self) -> int:
        """工作時數"""
        return self.get('WORK_HOURS', 9)
    
    @property
    def draw_cooldown(self) -> int:
        """抽獎冷卻時間（秒）"""
        return self.get('DRAW_COOLDOWN', 30)
    
    @property
    def max_queue_size(self) -> int:
        """最大佇列大小"""
        return self.get('MAX_QUEUE_SIZE', 50)
    
    @property
    def default_teams(self) -> int:
        """預設隊伍數量"""
        return self.get('DEFAULT_TEAMS', 2)
    
    @property
    def log_level(self) -> str:
        """日誌級別"""
        return self.get('LOG_LEVEL', 'INFO')
    
    @property
    def log_file(self) -> Optional[str]:
        """日誌檔案路徑"""
        return self.get('LOG_FILE')
    
    @property
    def data_dir(self) -> str:
        """資料目錄"""
        return self.get('DATA_DIR', 'data')
    
    @property
    def emoji_save_interval(self) -> int:
        """表情符號統計儲存間隔（秒）"""
        return self.get('EMOJI_SAVE_INTERVAL', 30)
    
    @property
    def reminder_cleanup_hours(self) -> int:
        """提醒清理間隔（小時）"""
        return self.get('REMINDER_CLEANUP_HOURS', 24)

# 全域配置實例
config = ConfigManager()