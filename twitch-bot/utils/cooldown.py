import time
from typing import Dict, Optional

class CooldownManager:
    """簡化的冷卻管理器"""
    
    def __init__(self):
        self.cooldowns: Dict[str, float] = {}
    
    def is_on_cooldown(self, key: str, cooldown_seconds: int) -> bool:
        """檢查是否在冷卻中"""
        current_time = time.time()
        
        if key in self.cooldowns:
            time_diff = current_time - self.cooldowns[key]
            if time_diff < cooldown_seconds:
                return True
        
        # 更新冷卻時間
        self.cooldowns[key] = current_time
        return False
    
    def get_remaining_cooldown(self, key: str, cooldown_seconds: int) -> Optional[float]:
        """獲取剩餘冷卻時間"""
        if key not in self.cooldowns:
            return None
        
        current_time = time.time()
        time_diff = current_time - self.cooldowns[key]
        
        if time_diff >= cooldown_seconds:
            return None
        
        return cooldown_seconds - time_diff
    
    def reset_cooldown(self, key: str):
        """重置指定冷卻"""
        if key in self.cooldowns:
            del self.cooldowns[key]
    
    def clear_all(self):
        """清除所有冷卻"""
        self.cooldowns.clear()
    
    def cleanup_expired(self, cooldown_seconds: int):
        """清理過期的冷卻記錄"""
        current_time = time.time()
        expired_keys = []
        
        for key, timestamp in self.cooldowns.items():
            if current_time - timestamp >= cooldown_seconds:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cooldowns[key]

class UserCooldown:
    """用戶專用冷卻管理器"""
    
    def __init__(self):
        self.cooldown_manager = CooldownManager()
    
    def check_user_command_cooldown(self, user: str, command: str, cooldown_seconds: int) -> bool:
        """檢查用戶指令冷卻"""
        key = f"{user}:{command}"
        return self.cooldown_manager.is_on_cooldown(key, cooldown_seconds)
    
    def check_global_command_cooldown(self, command: str, cooldown_seconds: int) -> bool:
        """檢查全域指令冷卻"""
        key = f"global:{command}"
        return self.cooldown_manager.is_on_cooldown(key, cooldown_seconds)
    
    def get_user_remaining_cooldown(self, user: str, command: str, cooldown_seconds: int) -> Optional[float]:
        """獲取用戶剩餘冷卻時間"""
        key = f"{user}:{command}"
        return self.cooldown_manager.get_remaining_cooldown(key, cooldown_seconds)