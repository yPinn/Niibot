"""JWT 認證服務"""

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import jwt
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from backend directory
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# JWT 設定
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"
# 配合 Twitch OAuth token 的有效期限
# Twitch tokens 通常不會過期,但建議定期重新驗證
# 設定為 30 天,可透過環境變數調整
ACCESS_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "30"))


def create_access_token(user_id: str) -> str:
    """建立 JWT access token

    Args:
        user_id: Twitch user ID

    Returns:
        str: JWT token
    """
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)

    payload = {
        "user_id": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc)
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    logger.info(f"Created JWT token for user_id: {user_id}")

    return token


def verify_token(token: str) -> Optional[str]:
    """驗證 JWT token 並返回 user_id

    Args:
        token: JWT token

    Returns:
        Optional[str]: user_id if valid, None if invalid/expired
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")

        if user_id is None:
            logger.warning("Token missing user_id")
            return None

        return str(user_id) if user_id else None

    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        return None
