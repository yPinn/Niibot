# config_local.py
import os

from dotenv import load_dotenv

load_dotenv()  # 載入 .env 檔案

TOKEN: str | None = os.getenv("TOKEN")
STATUS: str = "dnd"
# 可選: playing, streaming, listening, watching, competing
ACTIVITY_TYPE: str = "playing"
ACTIVITY_NAME: str = "Visual Studio Code"
USE_KEEP_ALIVE: bool = False
COMMAND_PREFIX: str = "?"
