"""Twitch 相關服務邏輯"""

import logging
from pathlib import Path
from urllib.parse import quote

import httpx

# 從 api config 載入配置
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import API_URL, BOT_URL, CLIENT_ID

# 從 twitch config 直接讀取 BROADCASTER_SCOPES
twitch_config_path = Path(__file__).parent.parent.parent / "twitch" / "config.py"
with open(twitch_config_path, encoding='utf-8') as f:
    exec(f.read(), globals())

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


async def forward_oauth_code_to_bot(code: str, scope: str | None = None) -> tuple[bool, str | None, str | None]:
    """將 OAuth code 轉發到 bot 進行處理

    Args:
        code: OAuth authorization code
        scope: OAuth scopes (optional)

    Returns:
        tuple[bool, str | None, str | None]: (是否成功, 錯誤訊息, user_id)
    """
    bot_oauth_url = f"{BOT_URL}/oauth/callback"
    params = {"code": code}
    if scope:
        params["scope"] = scope

    try:
        # 先取得目前資料庫中的 user_ids
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from services.database import get_database_pool

        pool = await get_database_pool()
        async with pool.acquire() as connection:
            existing_users = await connection.fetch("SELECT user_id FROM tokens")
            existing_user_ids = {row["user_id"] for row in existing_users}

        # 轉發 OAuth code 給 bot
        async with httpx.AsyncClient(follow_redirects=False, timeout=10.0) as client:
            response = await client.get(bot_oauth_url, params=params)

            if response.status_code >= 400:
                logger.error(f"Bot returned error status: {response.status_code}")
                return False, "bot_error", None

            logger.info(f"Successfully forwarded OAuth code to bot (status: {response.status_code})")

        # Bot 處理完後,查詢新增的 user_id
        async with pool.acquire() as connection:
            new_users = await connection.fetch("SELECT user_id FROM tokens")
            new_user_ids = {row["user_id"] for row in new_users}

        # 找出新增的 user_id
        added_users = new_user_ids - existing_user_ids

        if added_users:
            user_id = list(added_users)[0]
            logger.info(f"New user authorized: {user_id}")
            return True, None, user_id
        else:
            # 沒有新使用者,可能是重新授權
            # 從最後更新的 token 取得 user_id (假設是剛授權的)
            async with pool.acquire() as connection:
                row = await connection.fetchrow("SELECT user_id FROM tokens ORDER BY user_id DESC LIMIT 1")
                if row:
                    return True, None, row["user_id"]

            return True, None, None

    except httpx.TimeoutException:
        logger.error("Timeout while forwarding OAuth to bot")
        return False, "bot_timeout", None
    except httpx.ConnectError:
        logger.error("Cannot connect to bot (bot is offline or wrong port)")
        return False, "bot_offline", None
    except Exception as e:
        logger.exception(f"Unexpected error forwarding OAuth to bot: {e}")
        return False, "auth_failed", None
