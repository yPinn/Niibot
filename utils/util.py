import re
import time
from datetime import datetime, timezone, timedelta
import json
import os
import asyncio
import aiofiles
from typing import Any
import discord

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


async def write_json(path: str, data: Any) -> None:
    """
    非同步寫入 JSON 檔案，資料會漂亮列印且不轉 ASCII。
    """
    try:
        async with aiofiles.open(path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"[write_json_async] 寫入 {path} 失敗: {e}")

# --- 訊息格式化 ---


def format_error_msg(msg: str) -> str:
    """格式化錯誤訊息字串"""
    return f"❌ 錯誤：{msg}"


def format_success_msg(msg: str) -> str:
    """格式化成功訊息字串"""
    return f"✅ {msg}"


def create_activity(activity_type: str, name: str, url: str = None) -> discord.Activity:
    activity_type = activity_type.lower()

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
        raise ValueError(f"未知的 ACTIVITY_TYPE: {activity_type}")

# --- 簡易冷卻機制 ---


class Cooldown:
    def __init__(self, cooldown_seconds: int):
        self.cooldown = cooldown_seconds
        self._user_timestamps = {}

    def is_on_cooldown(self, user_id: int) -> bool:
        now = time.monotonic()
        last = self._user_timestamps.get(user_id, 0)
        return (now - last) < self.cooldown

    def update_timestamp(self, user_id: int):
        self._user_timestamps[user_id] = time.monotonic()

    async def wait_for_cooldown(self, user_id: int):
        while self.is_on_cooldown(user_id):
            await asyncio.sleep(1)
