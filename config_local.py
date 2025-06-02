# config_local.py
from dotenv import load_dotenv
import os

load_dotenv()  # 載入 .env 檔案

TOKEN = os.getenv("TOKEN")
STATUS = "online"
STREAM_NAME = "?help"
STREAM_URL = "https://www.twitch.tv/llazypilot"
USE_KEEP_ALIVE = False
COMMAND_PREFIX = "?"
