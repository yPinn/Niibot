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
                    TOKEN, STATUS, ACTIVITY_TYPE, ACTIVITY_NAME, ACTIVITY_URL,
                    USE_KEEP_ALIVE, COMMAND_PREFIX, TWITTER_BEARER_TOKEN, 
                    GOOGLE_TRANSLATE_API_KEY, BOT_ADMIN_IDS, TRUSTED_USER_IDS
                )
                activity_url = ACTIVITY_URL
            else:
                from config_local import (
                    TOKEN, STATUS, ACTIVITY_TYPE, ACTIVITY_NAME, ACTIVITY_URL,
                    USE_KEEP_ALIVE, COMMAND_PREFIX, TWITTER_BEARER_TOKEN, 
                    GOOGLE_TRANSLATE_API_KEY, BOT_ADMIN_IDS, TRUSTED_USER_IDS
                )
                activity_url = ACTIVITY_URL
            
            self._config = {
                'TOKEN': TOKEN,
                'STATUS': STATUS,
                'ACTIVITY_TYPE': ACTIVITY_TYPE,
                'ACTIVITY_NAME': ACTIVITY_NAME,
                'ACTIVITY_URL': activity_url,
                'USE_KEEP_ALIVE': USE_KEEP_ALIVE,
                'COMMAND_PREFIX': COMMAND_PREFIX,
                'BOT_ENV': env,
                
                # 權限系統配置
                'BOT_ADMIN_IDS': BOT_ADMIN_IDS,
                'TRUSTED_USER_IDS': TRUSTED_USER_IDS,
                
                # API 金鑰配置（從配置檔案載入）
                'TWITTER_BEARER_TOKEN': TWITTER_BEARER_TOKEN,
                'GOOGLE_TRANSLATE_API_KEY': GOOGLE_TRANSLATE_API_KEY,
                
                # 從環境變數或預設值載入其他配置
                'TARGET_ROLE_ID': int(os.getenv('TARGET_ROLE_ID', '1378242954929639514')),
                'WORK_HOURS': int(os.getenv('WORK_HOURS', '9')),
                'DRAW_COOLDOWN': int(os.getenv('DRAW_COOLDOWN', '30')),
                'MAX_QUEUE_SIZE': int(os.getenv('MAX_QUEUE_SIZE', '50')),
                'DEFAULT_TEAMS': int(os.getenv('DEFAULT_TEAMS', '2')),
                'LOG_LEVEL': os.getenv('LOG_LEVEL', 'WARNING'),
                'LOG_FILE': os.getenv('LOG_FILE', None),  # 生產環境不寫入檔案，避免權限問題
                'JSON_LOG_FILE': os.getenv('JSON_LOG_FILE', f'logs/niibot_{env}.json'),  # JSON 日誌檔案
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
        # 只對真正重要的配置項目發出警告
        if value is None and default is None and key in ['TOKEN']:
            BotLogger.warning("ConfigManager", f"必要配置項目 '{key}' 不存在")
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
        # 隱藏敏感資訊
        sensitive_keys = ['TOKEN', 'TWITTER_BEARER_TOKEN', 'GOOGLE_TRANSLATE_API_KEY']
        for key in sensitive_keys:
            if key in safe_config and safe_config[key]:
                safe_config[key] = '*' * 8
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
        prefix = self.get('COMMAND_PREFIX', '?')
        if isinstance(prefix, str):
            return [prefix]
        elif isinstance(prefix, list):
            return prefix
        else:
            return ['?']
    
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
    def json_log_file(self) -> Optional[str]:
        """JSON 日誌檔案路徑"""
        return self.get('JSON_LOG_FILE')
    
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
    
    @property
    def twitter_bearer_token(self) -> Optional[str]:
        """Twitter Bearer Token"""
        return self.get('TWITTER_BEARER_TOKEN')
    
    @property
    def google_translate_api_key(self) -> Optional[str]:
        """Google Translate API Key"""
        return self.get('GOOGLE_TRANSLATE_API_KEY')
    
    @property
    def bot_admin_ids(self) -> List[int]:
        """機器人管理員ID列表"""
        ids_str = self.get('BOT_ADMIN_IDS', '')
        if not ids_str:
            return []
        return [int(id.strip()) for id in ids_str.split(',') if id.strip()]
    
    @property
    def trusted_user_ids(self) -> List[int]:
        """信任用戶ID列表"""
        ids_str = self.get('TRUSTED_USER_IDS', '')
        if not ids_str:
            return []
        return [int(id.strip()) for id in ids_str.split(',') if id.strip()]

# 全域配置實例
config = ConfigManager()