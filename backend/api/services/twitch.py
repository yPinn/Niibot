"""Twitch 相關服務邏輯"""

import logging
import sys
from pathlib import Path
from urllib.parse import quote

import httpx

# 從 api config 載入配置
sys.path.insert(0, str(Path(__file__).parent.parent))
# 從 twitch config 載入 BROADCASTER_SCOPES
import importlib.util

from config import API_URL, CLIENT_ID

twitch_config_path = Path(__file__).parent.parent.parent / "twitch" / "config.py"
spec = importlib.util.spec_from_file_location("twitch_config", twitch_config_path)
if spec and spec.loader:
    twitch_config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(twitch_config)
    BROADCASTER_SCOPES = twitch_config.BROADCASTER_SCOPES
else:
    raise ImportError("Failed to load twitch config")

logger = logging.getLogger(__name__)


def generate_oauth_url() -> str:
    """生成 Twitch OAuth 授權 URL

    Returns:
        str: 完整的 OAuth 授權 URL
    """
    redirect_uri = f"{API_URL}/api/auth/twitch/callback"
    scope_string = "+".join(s.replace(":", "%3A") for s in BROADCASTER_SCOPES)
    encoded_redirect_uri = quote(redirect_uri, safe="")

    return (
        f"https://id.twitch.tv/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={encoded_redirect_uri}"
        f"&response_type=code"
        f"&scope={scope_string}"
        f"&force_verify=true"  # 強制顯示授權確認頁面
    )


async def exchange_code_for_token(code: str) -> tuple[bool, str | None, dict | None]:
    """用 OAuth code 換取 access token 和 user_id

    Args:
        code: OAuth authorization code

    Returns:
        tuple[bool, str | None, dict | None]: (是否成功, 錯誤訊息, token_data)
        token_data = {
            "access_token": str,
            "refresh_token": str,
            "user_id": str
        }
    """
    try:
        import os

        from dotenv import load_dotenv

        # Load CLIENT_SECRET from backend directory
        env_path = Path(__file__).parent.parent.parent / ".env"
        load_dotenv(dotenv_path=env_path)
        client_secret = os.getenv("CLIENT_SECRET")

        redirect_uri = f"{API_URL}/api/auth/twitch/callback"

        async with httpx.AsyncClient(timeout=10.0) as client:
            # 1. 用 code 換取 access_token
            token_response = await client.post(
                "https://id.twitch.tv/oauth2/token",
                data={
                    "client_id": CLIENT_ID,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri
                }
            )

            if token_response.status_code != 200:
                logger.error(f"Failed to exchange code for token: {token_response.status_code}")
                logger.error(f"Response: {token_response.text}")
                return False, "token_exchange_failed", None

            token_data = token_response.json()
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")

            if not access_token:
                logger.error("No access_token in response")
                return False, "no_access_token", None

            # 2. 用 access_token 取得 user_id
            user_response = await client.get(
                "https://api.twitch.tv/helix/users",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Client-Id": CLIENT_ID
                }
            )

            if user_response.status_code != 200:
                logger.error(f"Failed to get user info: {user_response.status_code}")
                return False, "user_fetch_failed", None

            user_data = user_response.json()
            users = user_data.get("data", [])

            if not users:
                logger.error("No user data in response")
                return False, "no_user_data", None

            user_id = users[0].get("id")

            if not user_id:
                logger.error("No user_id in user data")
                return False, "no_user_id", None

            logger.info(f"Successfully exchanged code for token, user_id: {user_id}")

            return True, None, {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user_id": user_id
            }

    except httpx.TimeoutException:
        logger.error("Timeout while exchanging code for token")
        return False, "timeout", None
    except Exception as e:
        logger.exception(f"Unexpected error exchanging code: {e}")
        return False, "exchange_failed", None


async def save_token_to_database(user_id: str, access_token: str, refresh_token: str | None) -> bool:
    """將 token 儲存到資料庫

    Args:
        user_id: Twitch user ID
        access_token: Twitch access token
        refresh_token: Twitch refresh token (可能為 None)

    Returns:
        bool: 是否成功
    """
    try:
        from services.database import get_database_pool

        pool = await get_database_pool()
        async with pool.acquire() as connection:
            # tokens 表結構: (user_id, token, refresh)
            await connection.execute(
                """
                INSERT INTO tokens (user_id, token, refresh)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id)
                DO UPDATE SET
                    token = EXCLUDED.token,
                    refresh = EXCLUDED.refresh
                """,
                user_id,
                access_token,
                refresh_token or ""  # 如果沒有 refresh_token 使用空字串
            )

        logger.info(f"Saved token to database for user_id: {user_id}")
        return True

    except Exception as e:
        logger.exception(f"Error saving token to database: {e}")
        return False


async def get_monitored_channels(user_id: str) -> list[dict]:
    """獲取監聽的頻道列表及其在線狀態

    Args:
        user_id: 當前登入的用戶 ID

    Returns:
        list[dict]: 頻道列表
        [
            {
                "id": "頻道 ID",
                "name": "頻道帳號",
                "display_name": "顯示名稱",
                "avatar": "頭像 URL",
                "is_live": true/false,
                "viewer_count": 觀看人數（如果在線）,
                "game_name": "遊戲名稱"（如果在線）
            }
        ]
    """
    try:
        from services.database import get_database_pool

        pool = await get_database_pool()

        # 1. 從資料庫獲取用戶的 access token
        async with pool.acquire() as connection:
            token_row = await connection.fetchrow(
                "SELECT token FROM tokens WHERE user_id = $1",
                user_id
            )

            if not token_row:
                logger.warning(f"No token found for user_id: {user_id}")
                return []

            access_token = token_row["token"]

            # 2. 從資料庫獲取監聽的頻道列表（從 channels 表）
            channel_rows = await connection.fetch(
                "SELECT DISTINCT channel_name FROM channels WHERE enabled = true"
            )

            logger.info(f"Found {len(channel_rows)} channel rows in database")

            if not channel_rows:
                logger.info("No monitored channels found")
                return []

            # 取得頻道名稱列表
            channel_names = [row["channel_name"] for row in channel_rows]
            logger.info(f"Channel names: {channel_names}")

        # 3. 使用 Twitch API 批次查詢頻道資訊
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 查詢用戶資訊
            users_response = await client.get(
                "https://api.twitch.tv/helix/users",
                params={"login": channel_names},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Client-Id": CLIENT_ID
                }
            )

            if users_response.status_code != 200:
                logger.error(f"Failed to fetch user info: {users_response.status_code}")
                logger.error(f"Response: {users_response.text}")
                return []

            users_data = users_response.json().get("data", [])
            logger.info(f"Twitch API returned {len(users_data)} users")

            # 建立頻道資訊字典（排除當前用戶自己）
            channels_info = {}
            for user in users_data:
                # 跳過當前登入的用戶
                if user["id"] == user_id:
                    continue

                channels_info[user["login"]] = {
                    "id": user["id"],
                    "name": user["login"],
                    "display_name": user["display_name"],
                    "avatar": user["profile_image_url"],
                    "is_live": False
                }

            # 查詢在線狀態
            user_ids = [user["id"] for user in users_data]
            if user_ids:
                streams_response = await client.get(
                    "https://api.twitch.tv/helix/streams",
                    params={"user_id": user_ids},
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Client-Id": CLIENT_ID
                    }
                )

                if streams_response.status_code == 200:
                    streams_data = streams_response.json().get("data", [])

                    # 更新在線狀態
                    for stream in streams_data:
                        user_id_str = stream["user_id"]
                        # 找到對應的頻道
                        for channel in channels_info.values():
                            if channel["id"] == user_id_str:
                                channel["is_live"] = True
                                channel["viewer_count"] = stream["viewer_count"]
                                channel["game_name"] = stream["game_name"]
                                break

        # 轉換為列表並排序（在線的排前面）
        result = list(channels_info.values())
        result.sort(key=lambda x: (not x["is_live"], x["display_name"]))

        logger.info(f"Found {len(result)} monitored channels for user {user_id}")
        return result

    except Exception as e:
        logger.exception(f"Error getting monitored channels: {e}")
        return []
