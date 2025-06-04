# config_prod.py

import os

TOKEN: str = os.getenv("TOKEN", "")  # 使用環境變數
STATUS: str = "online"
# 可選: playing, streaming, listening, watching, competing
ACTIVITY_TYPE: str = "streaming"
ACTIVITY_NAME: str = "若能向上天祈祷一睡不醒"
ACTIVITY_URL: str = "https://twitch.tv/xxx"  # 僅 streaming 需要
USE_KEEP_ALIVE: bool = True
COMMAND_PREFIX: list[str] = ["?"]
