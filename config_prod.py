# config_prod.py

import os

TOKEN: str = os.getenv("TOKEN")  # 使用環境變數，無預設值以避免空 token 問題
if not TOKEN:
    raise ValueError("TOKEN 環境變數未設定或為空值")
STATUS: str = "online"
# 可選: playing, streaming, listening, watching, competing
ACTIVITY_TYPE: str = "streaming"
ACTIVITY_NAME: str = "若能向上天祈祷一睡不醒"
ACTIVITY_URL: str = "https://twitch.tv/xxx"  # 僅 streaming 需要
USE_KEEP_ALIVE: bool = True  # 重新啟用，但改變啟動順序
COMMAND_PREFIX: list[str] = ["?"]
