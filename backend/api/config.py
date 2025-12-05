"""API Server 配置"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from twitch directory
env_path = Path(__file__).parent.parent / "twitch" / ".env"
load_dotenv(dotenv_path=env_path)

# API Server 配置
CLIENT_ID = os.getenv("CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
BOT_URL = os.getenv("BOT_URL", "http://localhost:4343")
API_URL = os.getenv("API_URL", "http://localhost:8000")

# CORS 設定
CORS_ORIGINS = [
    "http://localhost:3000",  # Frontend URL
    FRONTEND_URL,  # 允許自定義的前端 URL
]

# Logging 設定
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
