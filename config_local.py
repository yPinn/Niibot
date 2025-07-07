# config_local.py
import os

from dotenv import load_dotenv

load_dotenv()  # 載入 .env 檔案

TOKEN: str | None = os.getenv("TOKEN")
STATUS: str = "dnd"
# 可選: playing, streaming, listening, watching, competing
ACTIVITY_TYPE: str = "playing"
ACTIVITY_NAME: str = "Visual Studio Code"
ACTIVITY_URL: str | None = None  # 僅 streaming 需要
USE_KEEP_ALIVE: bool = False
COMMAND_PREFIX: list[str] = ["?", "❓"]

# 權限系統設定
BOT_ADMIN_IDS: str = os.getenv("BOT_ADMIN_IDS", "335342112973520896")  # 用逗號分隔的管理員ID
TRUSTED_USER_IDS: str = os.getenv("TRUSTED_USER_IDS", "")  # 用逗號分隔的信任用戶ID

# API 金鑰設定
TWITTER_BEARER_TOKEN: str | None = os.getenv("TWITTER_BEARER_TOKEN")
GOOGLE_TRANSLATE_API_KEY: str | None = os.getenv("GOOGLE_TRANSLATE_API_KEY")
