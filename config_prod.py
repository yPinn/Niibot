# config_prod.py

import os

TOKEN: str = os.getenv("TOKEN", "")  # 使用環境變數
STATUS: str = "online"
STREAM_NAME: str = "若能向上天祈祷一睡不醒"
STREAM_URL: str = "https://www.twitch.tv/llazypilot"
USE_KEEP_ALIVE: bool = True
COMMAND_PREFIX: str = "?"
