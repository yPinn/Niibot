"""使用者相關服務邏輯"""

import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load Twitch credentials from backend directory
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

CLIENT_ID = os.getenv("CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")


async def get_user_info(user_id: str) -> dict | None:
    """獲取指定使用者資訊

    使用 user_id 呼叫 Twitch API 取得最新資訊

    Args:
        user_id: Twitch user ID

    Returns:
        dict: 使用者資訊 {name, display_name, avatar}
        None: 查詢失敗
    """
    try:
        # 使用 App Access Token 呼叫 Twitch API
        # 首先取得 App Access Token
        async with httpx.AsyncClient(timeout=5.0) as client:
            # 取得 App Access Token
            token_response = await client.post(
                "https://id.twitch.tv/oauth2/token",
                params={
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "grant_type": "client_credentials"
                }
            )

            if token_response.status_code != 200:
                logger.error(f"Failed to get app access token: {token_response.status_code}")
                return None

            app_token = token_response.json().get("access_token")

            # 使用 App Access Token 查詢使用者資訊 (用 user_id 查詢)
            response = await client.get(
                f"https://api.twitch.tv/helix/users?id={user_id}",
                headers={
                    "Client-ID": CLIENT_ID,
                    "Authorization": f"Bearer {app_token}"
                }
            )

            if response.status_code != 200:
                logger.error(f"Failed to fetch user from Twitch API: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return None

            data = response.json()
            users = data.get("data", [])

            if not users:
                logger.warning(f"No user found for user_id: {user_id}")
                return None

            user = users[0]

            return {
                "name": user.get("login"),  # Twitch login name (username)
                "display_name": user.get("display_name"),  # Twitch display name
                "avatar": user.get("profile_image_url")  # Twitch avatar
            }

    except Exception as e:
        logger.exception(f"Error fetching user info: {e}")
        return None
