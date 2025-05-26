from datetime import datetime, timezone, timedelta
import json
import re
import asyncio
import os
import aiofiles

# 文字預處理


def normalize_text(text: str) -> str:
    """去除前後空白，轉小寫，移除多餘空白"""
    return ' '.join(text.strip().lower().split())


# 時間相關工具
def now_utc() -> datetime:
    """取得 UTC 現在時間"""
    return datetime.now(timezone.utc)


def now_local(tz_offset_hours=8) -> datetime:
    """取得本地時間，預設東八區"""
    return datetime.now(timezone(timedelta(hours=tz_offset_hours)))


def format_datetime(dt: datetime, fmt="%Y-%m-%d %H:%M:%S") -> str:
    """格式化 datetime 成字串"""
    return dt.strftime(fmt)


def parse_datetime(dt_str: str, fmt="%Y-%m-%d %H:%M:%S") -> datetime:
    """字串轉 datetime"""
    return datetime.strptime(dt_str, fmt)


def convert_timezone(dt: datetime, offset_hours: int) -> datetime:
    """將 datetime 轉成指定時區時間"""
    return dt.astimezone(timezone(timedelta(hours=offset_hours)))


# 錯誤與訊息格式化
def format_error_msg(msg: str) -> str:
    return f"❌ 錯誤：{msg}"


def format_success_msg(msg: str) -> str:
    return f"✅ {msg}"


# 簡單字串解析
def extract_params(command_str: str) -> list[str]:
    """簡單以空白分割，回傳參數列表（不含指令名稱）"""
    parts = command_str.strip().split()
    return parts[1:] if len(parts) > 1 else []


def fuzzy_match(keyword: str, text: str) -> bool:
    """簡單模糊匹配，忽略大小寫"""
    pattern = re.escape(keyword.lower())
    return re.search(pattern, text.lower()) is not None


# JSON 讀寫輔助
async def read_json(path: str):
    if not os.path.exists(path):
        return {}
    try:
        async with aiofiles.open(path, 'r', encoding='utf-8') as f:
            content = await f.read()
            if not content.strip():
                return {}
            return json.loads(content)
    except Exception as e:
        print(f"[read_json_async] 讀取 {path} 失敗: {e}")
        return {}


async def write_json(path: str, data):
    try:
        async with aiofiles.open(path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"[write_json_async] 寫入 {path} 失敗: {e}")


# 簡易冷卻機制
class Cooldown:
    def __init__(self, cooldown_seconds: int):
        self.cooldown = cooldown_seconds
        self._user_timestamps = {}

    def is_on_cooldown(self, user_id: int) -> bool:
        now = datetime.now().timestamp()
        last = self._user_timestamps.get(user_id, 0)
        return (now - last) < self.cooldown

    def update_timestamp(self, user_id: int):
        self._user_timestamps[user_id] = datetime.now().timestamp()

    async def wait_for_cooldown(self, user_id: int):
        while self.is_on_cooldown(user_id):
            await asyncio.sleep(1)
