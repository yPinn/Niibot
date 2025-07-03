import re
import time
from datetime import datetime, timezone, timedelta
import json
import os
import asyncio
import aiofiles
from typing import Any, Dict, List, Optional
import discord
from utils.logger import BotLogger
from utils.config_manager import config

# --- 文字處理工具 ---


def normalize_text(text: str) -> str:
    """去除前後空白，轉小寫，並將多重空白合併成一個空白"""
    text = text.strip().lower()
    return re.sub(r'\s+', ' ', text)


def fuzzy_match(keyword: str, text: str) -> bool:
    """忽略大小寫判斷 keyword 是否在 text 中"""
    return keyword.lower() in text.lower()


def extract_params(command_str: str) -> list[str]:
    """
    簡單將指令字串以空白分割，回傳參數列表(不含指令名稱本體)
    例如: "!eat 早餐 午餐" -> ["早餐", "午餐"]
    """
    parts = command_str.strip().split()
    return parts[1:] if len(parts) > 1 else []

# --- 時間相關工具 ---


def now_utc() -> datetime:
    """取得當前 UTC 時間（含時區）"""
    return datetime.now(timezone.utc)


def now_local(tz_offset_hours=8) -> datetime:
    """取得當前本地時間，預設為 UTC+8"""
    return datetime.now(timezone(timedelta(hours=tz_offset_hours)))


def format_datetime(dt: datetime, fmt="%Y-%m-%d %H:%M:%S") -> str:
    """將 datetime 格式化成字串"""
    return dt.strftime(fmt)


def parse_datetime(dt_str: str, fmt="%Y-%m-%d %H:%M:%S", tzinfo=None) -> datetime:
    dt = datetime.strptime(dt_str, fmt)
    if tzinfo is not None:
        dt = dt.replace(tzinfo=tzinfo)
    return dt


def convert_timezone(dt: datetime, offset_hours: int) -> datetime:
    """將 datetime 轉換成指定時區"""
    return dt.astimezone(timezone(timedelta(hours=offset_hours)))

# --- JSON 非同步讀寫工具 ---


async def read_json(path: str) -> dict[str, Any]:
    """
    非同步讀取 JSON 檔案。
    若檔案不存在或內容空白，回傳空 dict。
    """
    if not os.path.exists(path):
        BotLogger.debug("DataAccess", f"檔案不存在: {path}")
        return {}
    try:
        async with aiofiles.open(path, 'r', encoding='utf-8') as f:
            content = await f.read()
            if not content.strip():
                BotLogger.debug("DataAccess", f"檔案內容為空: {path}")
                return {}
            data = json.loads(content)
            BotLogger.debug("DataAccess", f"成功讀取: {path}")
            return data
    except Exception as e:
        BotLogger.error("DataAccess", f"讀取 JSON 檔案失敗: {path}", e)
        return {}


async def write_json(path: str, data: Any) -> bool:
    """
    非同步寫入 JSON 檔案，資料會漂亮列印且不轉 ASCII。
    
    Returns:
        bool: 寫入是否成功
    """
    try:
        # 確保目錄存在
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        async with aiofiles.open(path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))
        
        BotLogger.debug("DataAccess", f"成功寫入: {path}")
        return True
    except Exception as e:
        BotLogger.error("DataAccess", f"寫入 JSON 檔案失敗: {path}", e)
        return False

# --- 訊息格式化 ---


def format_error_msg(msg: str) -> str:
    """格式化錯誤訊息字串"""
    return f"❌ 錯誤：{msg}"


def format_success_msg(msg: str) -> str:
    """格式化成功訊息字串"""
    return f"✅ {msg}"


def create_activity(activity_type: str = None, name: str = None, url: str = None) -> discord.Activity:
    """建立 Discord 活動狀態
    
    Args:
        activity_type: 活動類型，若為 None 則從配置取得
        name: 活動名稱，若為 None 則從配置取得  
        url: 活動 URL（僅串流需要），若為 None 則從配置取得
        
    Returns:
        discord.Activity: Discord 活動物件
    """
    activity_type = (activity_type or config.activity_type).lower()
    name = name or config.activity_name
    url = url or config.activity_url

    try:
        if activity_type == "playing":
            return discord.Game(name=name)
        elif activity_type == "streaming":
            return discord.Streaming(name=name, url=url or "https://twitch.tv/")
        elif activity_type == "listening":
            return discord.Activity(type=discord.ActivityType.listening, name=name)
        elif activity_type == "watching":
            return discord.Activity(type=discord.ActivityType.watching, name=name)
        elif activity_type == "competing":
            return discord.Activity(type=discord.ActivityType.competing, name=name)
        else:
            BotLogger.error("ActivityCreator", f"未知的活動類型: {activity_type}")
            return discord.Game(name=name)  # 預設為遊戲狀態
    except Exception as e:
        BotLogger.error("ActivityCreator", "建立活動狀態失敗", e)
        return discord.Game(name="Discord Bot")  # 安全的預設值

# --- 簡易冷卻機制 ---


class Cooldown:
    """冷卻管理器"""
    
    def __init__(self, cooldown_seconds: int):
        self.cooldown = cooldown_seconds
        self._user_timestamps = {}
        self._cleanup_interval = 3600  # 1小時清理一次
        self._last_cleanup = time.monotonic()

    def is_on_cooldown(self, user_id: int) -> bool:
        """檢查用戶是否在冷卻中"""
        self._cleanup_old_entries()
        now = time.monotonic()
        last = self._user_timestamps.get(user_id, 0)
        return (now - last) < self.cooldown

    def update_timestamp(self, user_id: int):
        """更新用戶時間戳"""
        self._user_timestamps[user_id] = time.monotonic()
    
    def get_remaining_time(self, user_id: int) -> float:
        """取得剩餘冷卻時間（秒）"""
        if not self.is_on_cooldown(user_id):
            return 0.0
        
        now = time.monotonic()
        last = self._user_timestamps.get(user_id, 0)
        return max(0, self.cooldown - (now - last))
    
    def _cleanup_old_entries(self):
        """清理過期的時間戳記錄"""
        now = time.monotonic()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        
        old_count = len(self._user_timestamps)
        cutoff = now - self.cooldown * 2  # 保留冷卻時間的兩倍
        self._user_timestamps = {
            user_id: timestamp 
            for user_id, timestamp in self._user_timestamps.items() 
            if timestamp > cutoff
        }
        
        cleaned_count = old_count - len(self._user_timestamps)
        if cleaned_count > 0:
            BotLogger.debug("Cooldown", f"清理了 {cleaned_count} 個過期的冷卻記錄")
        
        self._last_cleanup = now

    async def wait_for_cooldown(self, user_id: int):
        while self.is_on_cooldown(user_id):
            await asyncio.sleep(1)


# --- 資料管理工具函數 ---

async def load_guild_data(file_name: str, guild_id: int, default_data: Any = None) -> Any:
    """載入特定伺服器的資料"""
    file_path = get_data_file_path(file_name)
    data = await read_json(file_path)
    guild_id_str = str(guild_id)
    
    if guild_id_str not in data:
        data[guild_id_str] = default_data or {}
        await write_json(file_path, data)
        BotLogger.debug("DataManager", f"建立新伺服器資料: {guild_id}")
    
    return data[guild_id_str]

async def save_guild_data(file_name: str, guild_id: int, guild_data: Any) -> bool:
    """儲存特定伺服器的資料"""
    file_path = get_data_file_path(file_name)
    data = await read_json(file_path)
    data[str(guild_id)] = guild_data
    return await write_json(file_path, data)


# --- 常用工具函數 ---

def get_data_file_path(file_name: str) -> str:
    """取得資料檔案的完整路徑"""
    return os.path.join(config.data_dir, file_name)


def ensure_data_dir() -> None:
    """確保資料目錄存在"""
    os.makedirs(config.data_dir, exist_ok=True)


def safe_get_member_display_name(member: discord.Member) -> str:
    """安全取得成員顯示名稱"""
    try:
        return member.display_name or member.name or "未知用戶"
    except:
        return "未知用戶"


def safe_get_channel_name(channel: discord.abc.GuildChannel) -> str:
    """安全取得頻道名稱"""
    try:
        return channel.name or "未知頻道"
    except:
        return "未知頻道"


def format_user_mention(user_id: int) -> str:
    """格式化用戶提及"""
    return f"<@{user_id}>"


def format_channel_mention(channel_id: int) -> str:
    """格式化頻道提及"""
    return f"<#{channel_id}>"


def format_role_mention(role_id: int) -> str:
    """格式化身分組提及"""
    return f"<@&{role_id}>"


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """截斷文字"""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def validate_input(text: str, max_length: int = 100, allowed_chars: str = None) -> bool:
    """驗證輸入文字
    
    Args:
        text: 要驗證的文字
        max_length: 最大長度
        allowed_chars: 允許的字符（正則表達式），None 表示不限制
        
    Returns:
        bool: 是否通過驗證
    """
    if not text or len(text) > max_length:
        return False
    
    if allowed_chars and not re.match(allowed_chars, text):
        return False
        
    return True


def get_deployment_info() -> str:
    """獲取部署環境信息
    
    Returns:
        str: 部署環境的詳細信息
    """
    deployment_info = []
    
    # 環境變數
    env = config.get('BOT_ENV', 'local')
    deployment_info.append(f"環境: {env}")
    
    # 主機名稱
    hostname = os.environ.get('HOSTNAME', 'unknown')
    deployment_info.append(f"主機: {hostname}")
    
    # 平台檢測
    platform_indicators = {
        'RENDER': 'Render',
        'RAILWAY_ENVIRONMENT': 'Railway', 
        'HEROKU_APP_NAME': 'Heroku',
        'VERCEL': 'Vercel',
        'REPLIT_ENVIRONMENT': 'Replit',
        'GITPOD_WORKSPACE_ID': 'Gitpod',
        'CODESPACE_NAME': 'GitHub Codespaces'
    }
    
    detected_platform = None
    for env_var, platform_name in platform_indicators.items():
        if os.environ.get(env_var):
            detected_platform = platform_name
            break
    
    if detected_platform:
        deployment_info.append(f"平台: {detected_platform}")
    else:
        deployment_info.append("平台: 本地或未知")
    
    # 特殊環境變數
    if os.environ.get('PORT'):
        deployment_info.append(f"端口: {os.environ.get('PORT')}")
    
    if os.environ.get('RENDER_SERVICE_NAME'):
        deployment_info.append(f"Render服務: {os.environ.get('RENDER_SERVICE_NAME')}")
    
    if os.environ.get('RAILWAY_SERVICE_NAME'):
        deployment_info.append(f"Railway服務: {os.environ.get('RAILWAY_SERVICE_NAME')}")
    
    # Python 版本
    import sys
    deployment_info.append(f"Python: {sys.version.split()[0]}")
    
    # 進程ID
    deployment_info.append(f"PID: {os.getpid()}")
    
    return " | ".join(deployment_info)


def get_version_info() -> str:
    """獲取版本資訊
    
    Returns:
        str: 版本資訊字串
    """
    import subprocess
    
    version_info = []
    
    try:
        # 嘗試獲取 Git commit hash
        result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            commit_hash = result.stdout.strip()
            version_info.append(f"Commit: {commit_hash}")
        else:
            version_info.append("Commit: unknown")
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        version_info.append("Commit: unknown")
    
    try:
        # 嘗試獲取 Git branch
        result = subprocess.run(['git', 'branch', '--show-current'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            branch = result.stdout.strip()
            if branch:
                version_info.append(f"Branch: {branch}")
            else:
                version_info.append("Branch: detached")
        else:
            version_info.append("Branch: unknown")
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        version_info.append("Branch: unknown")
    
    try:
        # 嘗試獲取最後提交時間
        result = subprocess.run(['git', 'log', '-1', '--format=%cd', '--date=iso'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            commit_date = result.stdout.strip()
            version_info.append(f"Last commit: {commit_date}")
        else:
            version_info.append("Last commit: unknown")
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        version_info.append("Last commit: unknown")
    
    # 檢查環境變數中的版本資訊
    if os.environ.get('HEROKU_SLUG_COMMIT'):
        version_info.append(f"Heroku commit: {os.environ.get('HEROKU_SLUG_COMMIT')[:7]}")
    
    if os.environ.get('RENDER_GIT_COMMIT'):
        version_info.append(f"Render commit: {os.environ.get('RENDER_GIT_COMMIT')[:7]}")
    
    if os.environ.get('RAILWAY_GIT_COMMIT_SHA'):
        version_info.append(f"Railway commit: {os.environ.get('RAILWAY_GIT_COMMIT_SHA')[:7]}")
    
    return " | ".join(version_info) if version_info else "Version info unavailable"


def get_uptime_info(startup_time) -> str:
    """獲取運行時間資訊
    
    Args:
        startup_time: 機器人啟動時間 (datetime object)
        
    Returns:
        str: 運行時間資訊字串
    """
    if not startup_time:
        return "啟動時間未知"
    
    from datetime import datetime
    current_time = datetime.now(datetime.UTC)
    uptime = current_time - startup_time
    
    # 計算天、小時、分鐘
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    # 格式化啟動時間
    startup_str = startup_time.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    # 格式化運行時間
    if days > 0:
        uptime_str = f"{days}天 {hours}小時 {minutes}分鐘"
    elif hours > 0:
        uptime_str = f"{hours}小時 {minutes}分鐘"
    else:
        uptime_str = f"{minutes}分鐘"
    
    return f"啟動時間: {startup_str} | 運行時間: {uptime_str}"
