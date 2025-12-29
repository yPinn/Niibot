"""API Server configuration"""

import os
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

CLIENT_ID = os.getenv("CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
BOT_URL = os.getenv("BOT_URL", "http://localhost:4343")
API_URL = os.getenv("API_URL", "http://localhost:8000")

CORS_ORIGINS = [FRONTEND_URL]
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
