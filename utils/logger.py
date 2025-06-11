import logging
import os
from datetime import datetime
from typing import Optional

class BotLogger:
    """統一的機器人日誌系統"""
    
    _logger = None
    _initialized = False
    
    @classmethod
    def initialize(cls, log_level: str = "INFO", log_file: Optional[str] = None):
        """初始化日誌系統
        
        Args:
            log_level: 日誌級別 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_file: 日誌檔案路徑，若為 None 則不寫入檔案
        """
        if cls._initialized:
            return
            
        cls._logger = logging.getLogger('niibot')
        cls._logger.setLevel(getattr(logging, log_level.upper()))
        
        # 清除既有的處理器
        cls._logger.handlers.clear()
        
        # 設定格式器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 控制台處理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        cls._logger.addHandler(console_handler)
        
        # 檔案處理器 (如果指定)
        if log_file:
            # 確保日誌目錄存在
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(formatter)
            cls._logger.addHandler(file_handler)
        
        cls._initialized = True
        cls.info("BotLogger", "日誌系統初始化完成")
    
    @classmethod
    def _get_logger(cls):
        """取得日誌器實例"""
        if not cls._initialized:
            cls.initialize()
        return cls._logger
    
    @classmethod
    def debug(cls, component: str, message: str, **kwargs):
        """除錯級別日誌"""
        cls._get_logger().debug(f"[{component}] {message}", extra=kwargs)
    
    @classmethod
    def info(cls, component: str, message: str, **kwargs):
        """資訊級別日誌"""
        cls._get_logger().info(f"[{component}] {message}", extra=kwargs)
    
    @classmethod
    def warning(cls, component: str, message: str, **kwargs):
        """警告級別日誌"""
        cls._get_logger().warning(f"[{component}] {message}", extra=kwargs)
    
    @classmethod
    def error(cls, component: str, message: str, error: Exception = None, **kwargs):
        """錯誤級別日誌"""
        error_msg = f"[{component}] {message}"
        if error:
            error_msg += f" - 錯誤詳情: {type(error).__name__}: {str(error)}"
        cls._get_logger().error(error_msg, extra=kwargs)
    
    @classmethod
    def critical(cls, component: str, message: str, error: Exception = None, **kwargs):
        """嚴重錯誤級別日誌"""
        error_msg = f"[{component}] {message}"
        if error:
            error_msg += f" - 錯誤詳情: {type(error).__name__}: {str(error)}"
        cls._get_logger().critical(error_msg, extra=kwargs)
    
    @classmethod
    def command_used(cls, command_name: str, user_id: int, guild_id: int, args: str = ""):
        """記錄指令使用情況"""
        cls.info("COMMAND", f"指令 '{command_name}' 被使用 - 用戶: {user_id}, 伺服器: {guild_id}, 參數: {args}")
    
    @classmethod
    def data_operation(cls, operation: str, file_path: str, success: bool = True, error: Exception = None):
        """記錄資料操作"""
        if success:
            cls.info("DATA", f"資料操作成功 - 操作: {operation}, 檔案: {file_path}")
        else:
            cls.error("DATA", f"資料操作失敗 - 操作: {operation}, 檔案: {file_path}", error)
    
    @classmethod
    def user_action(cls, action: str, user_id: int, guild_id: int, details: str = ""):
        """記錄用戶行為"""
        cls.info("USER", f"用戶行為 - 動作: {action}, 用戶: {user_id}, 伺服器: {guild_id}, 詳情: {details}")
    
    @classmethod
    def system_event(cls, event: str, details: str = ""):
        """記錄系統事件"""
        cls.info("SYSTEM", f"系統事件 - 事件: {event}, 詳情: {details}")