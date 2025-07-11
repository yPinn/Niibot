import logging
import os
from datetime import datetime

class TwitchLogger:
    """Twitch Bot 專用的簡化日誌系統"""
    
    _logger = None
    _initialized = False
    
    @classmethod
    def initialize(cls, log_level: str = "INFO", log_to_file: bool = True):
        """初始化日誌系統"""
        if cls._initialized:
            return
        
        cls._logger = logging.getLogger('twitch_bot')
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
        
        # 檔案處理器 (如果啟用)
        if log_to_file:
            # 確保日誌目錄存在
            log_dir = "../logs"
            os.makedirs(log_dir, exist_ok=True)
            
            file_handler = logging.FileHandler(f"{log_dir}/twitch.log", encoding='utf-8')
            file_handler.setFormatter(formatter)
            cls._logger.addHandler(file_handler)
        
        cls._initialized = True
        cls.info("TwitchLogger", "日誌系統初始化完成")
    
    @classmethod
    def get_logger(cls):
        """獲取 logger 實例"""
        if not cls._initialized:
            cls.initialize()
        return cls._logger
    
    @classmethod
    def info(cls, module: str, message: str):
        """記錄 INFO 級別日誌"""
        logger = cls.get_logger()
        logger.info(f"[{module}] {message}")
    
    @classmethod
    def warning(cls, module: str, message: str):
        """記錄 WARNING 級別日誌"""
        logger = cls.get_logger()
        logger.warning(f"[{module}] {message}")
    
    @classmethod
    def error(cls, module: str, message: str):
        """記錄 ERROR 級別日誌"""
        logger = cls.get_logger()
        logger.error(f"[{module}] {message}")
    
    @classmethod
    def debug(cls, module: str, message: str):
        """記錄 DEBUG 級別日誌"""
        logger = cls.get_logger()
        logger.debug(f"[{module}] {message}")
    
    @classmethod
    def command_log(cls, channel: str, user: str, command: str, result: str = "success"):
        """記錄指令執行"""
        cls.info("COMMAND", f"[{channel}] {user}: {command} -> {result}")
    
    @classmethod
    def system_event(cls, event: str, details: str = ""):
        """記錄系統事件"""
        message = f"系統事件 - 事件: {event}"
        if details:
            message += f", 詳情: {details}"
        cls.info("SYSTEM", message)