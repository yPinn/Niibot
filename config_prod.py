# config_prod.py

import os

TOKEN: str = os.getenv("TOKEN")  # 使用環境變數，無預設值以避免空 token 問題
if not TOKEN:
    raise ValueError("TOKEN 環境變數未設定或為空值")
STATUS: str = "online"
# 可選: playing, streaming, listening, watching, competing
ACTIVITY_TYPE: str = "streaming"
ACTIVITY_NAME: str = "若能向上天祈祷一睡不醒"
ACTIVITY_URL: str = "https://twitch.tv/31xuy"  # 僅 streaming 需要
USE_KEEP_ALIVE: bool = True  # 重新啟用，但改變啟動順序
COMMAND_PREFIX: str = "?"

# 權限系統設定
BOT_ADMIN_IDS: str = os.getenv("BOT_ADMIN_IDS", "")  # 用逗號分隔的管理員ID
TRUSTED_USER_IDS: str = os.getenv("TRUSTED_USER_IDS", "")  # 用逗號分隔的信任用戶ID

# API 金鑰設定
TWITTER_BEARER_TOKEN: str = os.getenv("TWITTER_BEARER_TOKEN", "")
GOOGLE_TRANSLATE_API_KEY: str = os.getenv("GOOGLE_TRANSLATE_API_KEY", "")
