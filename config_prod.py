# config_prod.py

import os

TOKEN = os.getenv("TOKEN")  # 使用環境變數
STATUS = "online"
STREAM_NAME = "若能向上天祈祷一睡不醒"
STREAM_URL = "https://www.twitch.tv/llazypilot"
USE_KEEP_ALIVE = True
COMMAND_PREFIX = "?"
