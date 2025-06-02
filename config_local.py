# config_local.py
import os

from dotenv import load_dotenv

load_dotenv()  # 載入 .env 檔案

TOKEN: str | None = os.getenv("TOKEN")
STATUS: str = "online"
STREAM_NAME: str = "?help"
STREAM_URL: str = "https://www.twitch.tv/llazypilot"
USE_KEEP_ALIVE: bool = False
COMMAND_PREFIX: list[str] = ["?", "❓"]
